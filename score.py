#!/usr/bin/env python3
"""Score a cablebench results folder: every cable is correct, wrong or abstained.

  python score.py --results bench/results/<run> --manifest bench/<items>/manifest.jsonl [--judge gpt-6-luna]

Per cable
  correct   value equals the gold right label (case-insensitive)
  wrong     any other value (also labels that do not exist on the right side)
  abstain   key missing, null, "", "unknown", "?", ... (old scorer counted JSON null as wrong)

Per run, the reason for missing cables (rules first, then optionally an LLM judge):
  honest_unknown   the model says it could not determine the cable(s) (explicit null etc.)
  broken_output    no parsable JSON although the model produced text, or keys silently missing
  technical        empty answer, crash, timeout, stream/reconnect failure
  refusal          the model declines (safety)

Metrics: accuracy = correct/n, coverage = answered/n, precision = correct/answered,
abstain_rate, penalized = (correct - wrong)/n (a wrong answer costs as much as a right one earns,
abstaining costs nothing), exact = all n correct.

Also works on old result folders (events.jsonl in the folder, no *.stats.json).
"""
import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

ABSTAIN_WORDS = {"", "null", "none", "unknown", "?", "??", "n/a", "na", "unsure", "unclear", "-", "--", "x",
                 "undetermined", "unresolved", "cannot determine", "not sure", "tbd"}
REFUSAL_RE = re.compile(r"(?i)\b(can.?t|cannot|won.?t|will not|unable to) (help|assist|provide|comply)|"
                        r"\bexplosive|\bbomb[- ]?(making|defus)|i must decline|i'm not able to help")
UNKNOWN_RE = re.compile(r"(?i)\b(unresolved|could not (be )?(determine|trace|resolve|follow)|can(no|')t (reliably )?"
                        r"(determine|trace|tell|resolve)|uncertain|not (reliably )?(traceable|determinable)|"
                        r"marked (as )?null|left (as )?null|ambiguous|i don.?t know|not confident)")
TECH_RE = re.compile(r"(?i)request timed out|stream disconnected|turn\.failed|internal server error|rate limit|"
                     r"usage limit|context (window|length)|429|5\d\d ")


# ----------------------------------------------------------------------------- parsing
def extract_json(text):
    """Return (dict or None, status) with status in ok | broken | none."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    cands = []
    try:
        return _as_map(json.loads(t)), "ok"
    except Exception:
        pass
    # largest {...} span, then every balanced block from the end
    if "{" in text and "}" in text:
        cands.append(text[text.find("{"): text.rfind("}") + 1])
        depth, start = 0, None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}" and depth:
                depth -= 1
                if depth == 0:
                    cands.append(text[start:i + 1])
        for c in sorted(cands, key=len, reverse=True):
            try:
                m = _as_map(json.loads(c))
                if m:
                    return m, "ok"
            except Exception:
                continue
        return None, "broken"
    return None, "none"


def _as_map(obj):
    if isinstance(obj, dict) and len(obj) == 1 and isinstance(next(iter(obj.values())), dict):
        obj = next(iter(obj.values()))  # {"answer": {...}}
    if not isinstance(obj, dict):
        raise ValueError
    return obj


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v).strip()


def is_abstain(v):
    return v is None or v.strip().lower().strip(".") in ABSTAIN_WORDS


def score_cables(pred, gold, right_labels):
    pmap = {}
    for k, v in (pred or {}).items():
        pmap[str(k).strip().lower()] = norm(v)
    rows, explicit_null = {}, 0
    rset = {r.lower() for r in right_labels} if right_labels else None
    for lab, g in gold.items():
        key = lab.strip().lower()
        if key not in pmap:
            rows[lab] = ("abstain", "missing", None)
            continue
        v = pmap[key]
        if is_abstain(v):
            explicit_null += 1
            rows[lab] = ("abstain", "explicit", v)
        elif v.lower() == str(g).lower():
            rows[lab] = ("correct", "", v)
        else:
            rows[lab] = ("wrong", "invalid_label" if rset and v.lower() not in rset else "", v)
    return rows, explicit_null


# ----------------------------------------------------------------------------- run info
def old_events_info(path):
    info = dict(reconnects=0, errors=[], turn_failed=False, turn_completed=False, commands=0, agent_messages=[],
                input_tokens=None, output_tokens=None, reasoning_tokens=None)
    if not os.path.exists(path):
        return info
    for line in open(path, encoding="utf-8-sig", errors="replace"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        ty, item = o.get("type"), o.get("item") or {}
        msg = o.get("message") or item.get("message") or (o.get("error") or {}).get("message") or ""
        if ty == "error" or (ty == "item.completed" and item.get("type") == "error"):
            if re.search(r"^`\[features\]|^Under-development features|is deprecated", msg):
                continue
            if "Reconnecting" in msg:
                info["reconnects"] += 1
            else:
                info["errors"].append(msg[:200])
        if ty == "turn.failed":
            info["turn_failed"] = True
        if ty == "turn.completed":
            info["turn_completed"] = True
            u = o.get("usage") or {}
            info.update(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                        reasoning_tokens=u.get("reasoning_output_tokens"))
        if ty == "item.completed" and item.get("type") == "command_execution":
            info["commands"] += 1
        if ty == "item.completed" and item.get("type") == "agent_message":
            info["agent_messages"].append(item.get("text", ""))
    return info


def rule_reason(text, status, n_abs, n_explicit, n_missing, info, timed_out):
    """Why cables are missing, from rules only. Returns (reason, evidence)."""
    if n_abs == 0:
        return "", ""
    msgs = " ".join(info.get("agent_messages") or [])[-3000:]
    if not text.strip():
        ev = []
        if timed_out:
            ev.append("timeout")
        if info.get("turn_failed"):
            ev.append("turn.failed")
        if info.get("errors"):
            ev.append("error: " + info["errors"][-1][:80])
        if info.get("reconnects"):
            ev.append(f"{info['reconnects']} reconnects")
        if REFUSAL_RE.search(msgs):
            return "refusal", "empty answer, refusal wording in messages"
        return "technical", ", ".join(ev) or "empty answer"
    if n_abs == n_explicit + n_missing and REFUSAL_RE.search(text) and (n_missing == n_abs or status != "ok"):
        return "refusal", "refusal wording" + ("" if status == "ok" else ", no JSON")
    if status != "ok":
        if REFUSAL_RE.search(text):
            return "refusal", "no JSON, refusal wording"
        if TECH_RE.search(text) and len(text) < 400:
            return "technical", "error text instead of an answer"
        return "broken_output", f"JSON {status}"
    if n_explicit and (UNKNOWN_RE.search(text) or UNKNOWN_RE.search(msgs) or n_explicit == n_abs):
        return "honest_unknown", f"{n_explicit} explicit null/unknown" + (", says so in text" if UNKNOWN_RE.search(text + msgs) else "")
    if n_missing and UNKNOWN_RE.search(text + msgs):
        return "honest_unknown", f"{n_missing} keys left out, says it could not determine them"
    return "broken_output", f"{n_missing} keys silently missing"


# ----------------------------------------------------------------------------- judge
JUDGE_PROMPT = """You classify why a model's answer to a cable-tracing puzzle is incomplete.
The model had to return a JSON object mapping every left label to a right label.
{n_abs} of {n} labels have no usable answer ({n_explicit} given as null/unknown, {n_missing} missing).
Technical signals from the harness: {signals}
Reconnect attempts and transport fallbacks are common and harmless when the turn completed and the model wrote an answer;
only call a run technical if the answer is missing, cut off or replaced by an error.

Final answer text (may be truncated):
<<<
{answer}
>>>

Earlier messages of the model (may be truncated):
<<<
{messages}
>>>

Classes:
- honest_unknown: the model deliberately leaves cables open because it is not sure (says so or uses null on purpose).
- broken_output: the model meant to answer fully but the output is malformed, truncated, a placeholder or keys are silently dropped.
- technical: the run broke (empty answer, crash, timeout, connection errors).
- refusal: the model declines the task.

Reply with one JSON object only: {{"class": "<one of the four>", "reason": "<one short sentence>"}}"""


def run_judge(rows_needing, judge_model, effort="low"):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench"))
    import run_bench as rb  # noqa: E402
    import shutil
    import subprocess
    import tempfile
    cmd = rb.codex_cmd()
    root = tempfile.mkdtemp(prefix="cbjudge_")
    main_home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    auth = os.path.join(main_home, "auth.json")
    scratch = os.path.join(root, "h_cat")
    os.makedirs(scratch)
    shutil.copy(auth, os.path.join(scratch, "auth.json"))
    cats, _ = rb.write_catalogs(cmd, root, judge_model, scratch)

    import types
    A = types.SimpleNamespace(model=judge_model, effort=effort)
    out = {}
    for key, ctx in rows_needing.items():
        h = rb.make_home(root, "j" + str(len(out)), "single", A, cats, auth)
        w = os.path.join(root, "w" + str(len(out)))
        os.makedirs(w)
        last = os.path.join(w, "last.txt")
        prompt = JUDGE_PROMPT.format(**ctx)
        pr = subprocess.run(cmd + ["exec", "--skip-git-repo-check", "-C", w, "-m", judge_model, "-s", "read-only",
                                   "--output-last-message", last, "-"], input=prompt.encode("utf-8"),
                            capture_output=True, env=dict(os.environ, CODEX_HOME=h), cwd=w)
        txt = open(last, encoding="utf-8").read() if os.path.exists(last) else ""
        m, _ = extract_json(txt)
        if m and m.get("class") in ("honest_unknown", "broken_output", "technical", "refusal"):
            out[key] = {"class": m["class"], "reason": str(m.get("reason", ""))[:300], "model": judge_model}
        else:
            out[key] = {"class": None, "reason": f"judge output unparsable: {txt[:120]}", "model": judge_model}
        print(f"judge {key}: {out[key]['class']}  {out[key]['reason'][:100]}", flush=True)
    for d in os.listdir(root):
        p = os.path.join(root, d, "auth.json")
        if os.path.exists(p):
            os.remove(p)
    return out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--judge", default="", help="model slug for the LLM judge (e.g. gpt-6-luna); empty = rules only")
    ap.add_argument("--traces", default="", help="private traces folder of this run (for agent messages)")
    ap.add_argument("--mode-alias", default="", help="rename modes of old runs, e.g. toolless=js_nofs")
    a = ap.parse_args()
    gold = {}
    for l in open(a.manifest, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            gold[r["id"]] = r
    alias = dict(x.split("=") for x in a.mode_alias.split(",") if x)
    traces = a.traces or os.path.join(os.path.expanduser("~"), "cablebench-traces", os.path.basename(os.path.normpath(a.results)))
    tags = sorted(os.path.basename(p)[:-len(".answer.txt")] for p in glob.glob(os.path.join(a.results, "*.answer.txt")))
    old_summary = {}
    sp = os.path.join(a.results, "summary.json")
    if os.path.exists(sp):
        try:
            for r in json.load(open(sp, encoding="utf-8-sig")):
                old_summary[f"{r['id']}_{r['mode']}_r{r.get('repeat', 1)}"] = r
        except Exception:
            pass
    prev_judge = {}
    jp = os.path.join(a.results, "judge.json")
    if os.path.exists(jp):
        prev_judge = json.load(open(jp, encoding="utf-8"))

    rows, per_cable, preds, need_judge = [], [], [], {}
    for tag in tags:
        m = re.match(r"(.+)_([a-z_]+?)_r(\d+)$", tag)
        iid, mode, rep = m.group(1), m.group(2), int(m.group(3))
        g = gold.get(iid)
        if g is None:
            continue
        text = open(os.path.join(a.results, tag + ".answer.txt"), encoding="utf-8-sig", errors="replace").read()
        stp = os.path.join(a.results, tag + ".stats.json")
        st = json.load(open(stp, encoding="utf-8")) if os.path.exists(stp) else {}
        info = old_events_info(os.path.join(a.results, tag + ".events.jsonl"))
        if st:
            info.update({k: st.get(k) for k in ("reconnects", "errors", "turn_failed", "turn_completed")})
        mp = os.path.join(traces, tag, "messages.json")
        if os.path.exists(mp):
            info["agent_messages"] = json.load(open(mp, encoding="utf-8")).get("assistant_messages", [])
        osr = old_summary.get(tag, {})
        timed_out = bool(st.get("timed_out", osr.get("timed_out", False)))
        pred, status = extract_json(text)
        cab, n_explicit = score_cables(pred, g["answer"], list(g["answer"].values()))
        cnt = collections.Counter(c[0] for c in cab.values())
        n = len(cab)
        n_abs = cnt["abstain"]
        n_missing = sum(1 for c in cab.values() if c[1] == "missing")
        reason, evidence = rule_reason(text, status, n_abs, n_explicit, n_missing, info, timed_out)
        answered = cnt["correct"] + cnt["wrong"]
        given = [c[2].lower() for c in cab.values() if c[0] != "abstain"]
        if st:
            tools = sum((st.get("tool_calls") or {}).values())
            nested = st.get("nested_calls") or {}
            cmds = nested.get("exec_command", 0)
        else:
            tools = cmds = info["commands"] or osr.get("commands_run", 0)
            nested = {}
        row = dict(tag=tag, id=iid, mode=alias.get(mode, mode), repeat=rep, n_cables=g["n_cables"], n_crossings=g.get("n_crossings"),
                   theme=g.get("theme"), correct=cnt["correct"], wrong=cnt["wrong"], abstain=n_abs, total=n,
                   accuracy=round(cnt["correct"] / n, 4), coverage=round(answered / n, 4),
                   precision=round(cnt["correct"] / answered, 4) if answered else None,
                   abstain_rate=round(n_abs / n, 4), penalized=round((cnt["correct"] - cnt["wrong"]) / n, 4),
                   exact=cnt["correct"] == n, json_status=status, explicit_null=n_explicit, missing_keys=n_missing,
                   duplicate_targets=len(given) - len(set(given)),
                   invalid_labels=sum(1 for c in cab.values() if c[1] == "invalid_label"),
                   abstain_reason_rule=reason, abstain_evidence=evidence,
                   abstain_reason_judge=None, judge_note=None,
                   seconds=st.get("seconds", osr.get("seconds")), timed_out=timed_out,
                   requests=st.get("requests"), tool_calls=tools, shell_commands=cmds,
                   view_image_calls=nested.get("view_image", (st.get("tool_calls") or {}).get("view_image", 0)),
                   input_tokens=st.get("input_tokens", info.get("input_tokens") or osr.get("input_tokens")),
                   output_tokens=st.get("output_tokens", info.get("output_tokens") or osr.get("output_tokens")),
                   reasoning_tokens=st.get("reasoning_tokens", info.get("reasoning_tokens") or osr.get("reasoning_tokens")),
                   reconnects=info.get("reconnects"), leak_suspect=bool(st.get("leak_suspect")),
                   prompt_variant=st.get("prompt_variant", "default"))
        if tag in prev_judge:
            row["abstain_reason_judge"] = prev_judge[tag]["class"]
            row["judge_note"] = prev_judge[tag]["reason"]
        elif n_abs and a.judge:
            sig = ["turn completed normally" if info.get("turn_completed") and not info.get("turn_failed") else "turn did NOT complete"]
            if timed_out:
                sig.append("timeout")
            if info.get("turn_failed"):
                sig.append("turn failed")
            if info.get("reconnects"):
                sig.append(f"{info['reconnects']} reconnect attempts")
            if info.get("errors"):
                sig.append("errors: " + "; ".join(e[:80] for e in info["errors"][-2:]))
            need_judge[tag] = dict(n=n, n_abs=n_abs, n_explicit=n_explicit, n_missing=n_missing,
                                   signals=", ".join(sig) or "none", answer=text[-3500:] or "(empty)",
                                   messages="\n---\n".join(info.get("agent_messages", [])[-4:-1])[-3000:] or "(none)")
        rows.append(row)
        preds.append({"id": iid, "mode": row["mode"], "repeat": rep, "answer": text})
        for lab, (cls, sub, v) in cab.items():
            per_cable.append(dict(id=iid, mode=row["mode"], repeat=rep, label=lab, gold=g["answer"][lab], pred=v,
                                  cls=cls, sub=sub))

    if need_judge:
        res = run_judge(need_judge, a.judge)
        prev_judge.update(res)
        json.dump(prev_judge, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        for r in rows:
            if r["tag"] in res:
                r["abstain_reason_judge"], r["judge_note"] = res[r["tag"]]["class"], res[r["tag"]]["reason"]

    json.dump(rows, open(os.path.join(a.results, "score.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(a.results, "score.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(a.results, "score_cables.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_cable[0]))
        w.writeheader()
        w.writerows(per_cable)
    with open(os.path.join(a.results, "predictions.jsonl"), "w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"{'id':16s} {'mode':9s} {'ok':>3s} {'bad':>3s} {'abs':>3s} {'/n':>4s}  {'prec':>5s} {'pen':>6s}  reason (rule / judge)")
    for r in sorted(rows, key=lambda r: (r["mode"], r["n_cables"], r["id"])):
        pr = f"{r['precision']:.2f}" if r["precision"] is not None else "  -  "
        print(f"{r['id'][:16]:16s} {r['mode'][:9]:9s} {r['correct']:3d} {r['wrong']:3d} {r['abstain']:3d} {r['total']:4d}  {pr:>5s} {r['penalized']:+.2f}  "
              f"{r['abstain_reason_rule'] or '-'} / {r['abstain_reason_judge'] or '-'}")
    agg = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        for k in ("correct", "wrong", "abstain", "total"):
            agg[r["mode"]][k] += r[k]
        agg[r["mode"]]["runs"] += 1
    print()
    for md, c in agg.items():
        ans = c["correct"] + c["wrong"]
        print(f"{md:10s} runs={c['runs']:3d} acc={c['correct'] / c['total']:.3f} cov={ans / c['total']:.3f} "
              f"prec={(c['correct'] / ans if ans else 0):.3f} abstain={c['abstain'] / c['total']:.3f} "
              f"penalized={(c['correct'] - c['wrong']) / c['total']:+.3f}")


if __name__ == "__main__":
    main()
