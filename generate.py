#!/usr/bin/env python3
"""Generate a cable-tracing benchmark set.

Example:
  python generate.py --out data/v1 --count 30 --n 6,10,16 --themes all --res auto
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cablebench.puzzle import PuzzleConfig            # noqa: E402
from cablebench.render import make_one, overlay        # noqa: E402
from cablebench.themes import THEMES                   # noqa: E402

LABEL_HELP = {
    "symbols": "Left ports are marked with shape icons. Use these names: circle, square, triangle, diamond, "
               "hexagon, star, cross, ring, pentagon, bar, chevron, dot.",
    "waves": "Left ports are marked with waveform icons. Use these names: sine, square, saw, triangle, noise, "
             "pulse, steps, ramp_down.",
}


def auto_res(n, cap_h=2160):
    h = min(max(900, int(70 * n)), cap_h)
    return (int(round(h * 16 / 9 / 16) * 16), int(round(h / 16) * 16))


def make_prompt(meta):
    left = meta["left_labels"]
    kind = None
    if all(l in LABEL_HELP["symbols"] for l in left) and not left[0].isdigit():
        kind = "symbols"
    if meta["theme"] == "synth" and left[0] in ("sine", "square", "saw", "triangle", "noise", "pulse", "steps", "ramp_down"):
        kind = "waves"
    p = ("The image shows a panel with cables. Every port on the left side is connected by exactly one cable "
         "to exactly one connector on the right side. Follow each cable and report where it ends.\n")
    if kind:
        p += LABEL_HELP[kind] + "\n"
    p += "Left labels from top to bottom: " + ", ".join(left) + ".\n"
    p += ('Answer with a JSON object that maps every left label to the right label its cable ends at, '
          'for example {"' + left[0] + '": "' + meta["right_labels"][0] + '", ...}.')
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sample")
    ap.add_argument("--count", type=int, default=6, help="images per (theme, n) combination")
    ap.add_argument("--n", default="8", help="comma list of cable counts")
    ap.add_argument("--themes", default="all")
    ap.add_argument("--color-mode", default="uniform", choices=["uniform", "few", "unique"])
    ap.add_argument("--res", default="1600x900", help="WxH or 'auto' (scales with n)")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-extras", action="store_true", help="no clips / occluders")
    ap.add_argument("--debug-overlay", action="store_true")
    ap.add_argument("--waypoints", default="2,4")
    ap.add_argument("--min-angle", type=float, default=25.0)
    a = ap.parse_args()

    themes = list(THEMES) if a.themes == "all" else a.themes.split(",")
    ns = [int(x) for x in a.n.split(",")]
    os.makedirs(a.out, exist_ok=True)
    manifest = open(os.path.join(a.out, "manifest.jsonl"), "a")
    k = 0
    for n in ns:
        for t in themes:
            for c in range(a.count):
                seed = a.seed + 100003 * n + 1009 * themes.index(t) + c
                res = auto_res(n) if a.res == "auto" else tuple(int(v) for v in a.res.split("x"))
                cfg = PuzzleConfig(n_cables=n, seed=seed, min_cross_angle_deg=a.min_angle,
                                   waypoints=tuple(int(v) for v in a.waypoints.split(",")))
                name = f"{t}_n{n:02d}_{seed}"
                t0 = time.time()
                try:
                    img, meta = make_one(a.out, name, THEMES[t], cfg, color_mode=a.color_mode, res=res,
                                         samples=a.samples, seed=seed, extras=not a.no_extras)
                except RuntimeError as e:
                    print(f"skip {name}: {e}", flush=True)
                    continue
                if a.debug_overlay:
                    overlay(img, meta, img.replace(".png", "_gt.png"))
                rec = dict(id=name, image=meta["image"], theme=t, n_cables=n, color_mode=a.color_mode,
                           prompt=make_prompt(meta), answer=meta["solution"],
                           n_crossings=meta["stats"]["n_crossings"],
                           occluded=bool(meta["notes"].get("occluder")))
                manifest.write(json.dumps(rec) + "\n")
                manifest.flush()
                k += 1
                print(f"[{k}] {name} {res[0]}x{res[1]} crossings={rec['n_crossings']} {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
