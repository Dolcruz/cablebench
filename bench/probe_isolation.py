#!/usr/bin/env python3
"""Check what a model would see in an isolated Codex home, without calling the model.

Uses `codex debug prompt-input` (renders the model-visible prompt list as JSON) and reports
top-level tools, tools nested in the JavaScript `exec` (code mode) tool, skills, AGENTS.md,
MCP and leaks of the user name / home path.

  python bench/probe_isolation.py --home C:/cbtest/h1 --cwd C:/cbtest/w1 [--image puzzle.png]
  python bench/probe_isolation.py --rollout path/to/rollout.jsonl     (same report from a real run)

Exit code 0 only if the expectation given with --expect holds:
  --expect none     no tools at all
  --expect look     only view_image (directly or nested)
  --expect code     anything, but no skills / AGENTS.md / MCP
"""
import argparse
import json
import os
import re
import subprocess
import sys


def nested_names(desc):
    return re.findall(r"^### `([^`]+)`", desc or "", re.M)


def analyse(items):
    rep = {"tools": [], "nested": [], "skills": [], "agents_md": False, "mcp": [], "leaks": [],
           "developer_blocks": [], "n_images": 0}
    for it in items:
        if it.get("type") == "additional_tools":
            for ns in it.get("tools", []):
                for t in ns.get("tools", [ns]) if ns.get("type") == "namespace" else [ns]:
                    name = (f"{ns.get('name')}.{t.get('name')}" if ns.get("type") == "namespace" else (t.get("name") or t.get("type")))
                    rep["tools"].append(name)
                    if t.get("name") == "exec":
                        rep["nested"] += nested_names(t.get("description"))
                    if "mcp" in (t.get("name") or ""):
                        rep["mcp"].append(name)
        if it.get("type") == "message":
            for c in it.get("content", []):
                if c.get("type") == "input_image":
                    rep["n_images"] += 1
                txt = c.get("text") or ""
                if it.get("role") == "developer" and txt:
                    rep["developer_blocks"].append(re.sub(r"\s+", " ", txt[:70]))
                if "<skills_instructions>" in txt or "### Available skills" in txt:
                    rep["skills"] += re.findall(r"^- ([\w.-]+): ", txt, re.M)
                if "AGENTS.md" in txt and "instructions" in txt.lower() and "<INSTRUCTIONS>" in txt:
                    rep["agents_md"] = True
                if "mcp_servers" in txt or "<mcp" in txt:
                    rep["mcp"].append("mcp text block")
    blob = json.dumps(items, ensure_ascii=False)
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    for pat in filter(None, [user, os.path.expanduser("~").replace("\\", "/"), os.path.expanduser("~").replace("\\", "\\\\")]):
        if len(pat) >= 3 and pat in blob:
            rep["leaks"].append(pat)
    return rep


def from_rollout(path):
    items = []
    import gzip
    opener = gzip.open if path.endswith(".gz") else open
    for line in opener(path, "rt", encoding="utf-8"):
        o = json.loads(line)
        if o.get("type") == "response_item" and o["payload"].get("type") in ("additional_tools", "message"):
            items.append(o["payload"])
            if o["payload"].get("type") == "message" and o["payload"].get("role") == "assistant":
                break
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home")
    ap.add_argument("--cwd")
    ap.add_argument("--image")
    ap.add_argument("--rollout")
    ap.add_argument("--expect", choices=["none", "look", "code"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.rollout:
        items = from_rollout(a.rollout)
    else:
        env = dict(os.environ, CODEX_HOME=a.home)
        cmd = ["codex", "debug", "prompt-input"] + (["-i", a.image] if a.image else []) + ["probe"]
        out = subprocess.run(cmd, cwd=a.cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                             shell=(os.name == "nt"))
        if out.returncode:
            print(out.stderr, file=sys.stderr)
            sys.exit(2)
        items = json.loads(out.stdout)
    rep = analyse(items)
    if a.json:
        print(json.dumps(rep, indent=1))
    else:
        print("tools:   ", rep["tools"])
        print("nested:  ", rep["nested"])
        print("skills:  ", rep["skills"])
        print("agents_md:", rep["agents_md"], " mcp:", rep["mcp"], " images:", rep["n_images"])
        print("leaks:   ", rep["leaks"])
        print("developer blocks:", *rep["developer_blocks"], sep="\n   ")
    ok = True
    if a.expect:
        ok = expectation_ok(rep, a.expect)
        print("EXPECT", a.expect, "OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


CODE_FORBIDDEN = {"spawn_agent", "followup_task", "send_message", "wait_agent", "image_gen__imagegen", "imagegen",
                  "create_goal", "update_goal", "get_goal", "tool_search", "request_user_input", "sleep"}


def expectation_ok(rep, expect):
    bad_ctx = rep["skills"] or rep["agents_md"] or rep["mcp"] or rep["leaks"]
    allt = set(t.split(".")[-1] for t in rep["tools"]) | set(rep["nested"])
    if expect == "none":
        return not allt and not bad_ctx
    if expect == "look":
        return allt == {"view_image"} and not bad_ctx
    return not bad_ctx and not (allt & CODE_FORBIDDEN) and "exec_command" in allt


if __name__ == "__main__":
    main()
