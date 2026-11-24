#!/usr/bin/env python3
"""Score model answers against the manifest.

predictions.jsonl: one line per item: {"id": "...", "answer": {"A": "3", ...}}
(the answer may also be the raw model text; the first {...} block is parsed)
"""
import argparse
import collections
import json
import re


def parse(ans):
    if isinstance(ans, dict):
        return {str(k).strip(): str(v).strip() for k, v in ans.items()}
    m = re.search(r"\{.*\}", ans, re.S)
    if not m:
        return {}
    try:
        return {str(k).strip(): str(v).strip() for k, v in json.loads(m.group(0)).items()}
    except json.JSONDecodeError:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("predictions")
    a = ap.parse_args()
    gold = {json.loads(l)["id"]: json.loads(l) for l in open(a.manifest)}
    by = collections.defaultdict(lambda: [0, 0, 0, 0])  # cables_ok, cables, exact, items
    for line in open(a.predictions):
        p = json.loads(line)
        g = gold.get(p["id"])
        if g is None:
            continue
        pred = parse(p["answer"])
        ok = sum(pred.get(k, "").lower() == v.lower() for k, v in g["answer"].items())
        for key in ("all", f"n={g['n_cables']}", f"theme={g['theme']}"):
            b = by[key]
            b[0] += ok; b[1] += len(g["answer"]); b[2] += ok == len(g["answer"]); b[3] += 1
    for key in sorted(by, key=lambda s: (s != "all", s)):
        c, t, e, i = by[key]
        print(f"{key:20s} items={i:4d}  per-cable={c / t:6.1%}  exact={e / i:6.1%}")


if __name__ == "__main__":
    main()
