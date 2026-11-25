#!/usr/bin/env python3
"""Layout check for labels: render one routed puzzle in every theme with 3-digit right labels.

  .venv\\Scripts\\python.exe bench/label_test.py <puzzle.pkl> <out_dir> [label_scale]
Writes <theme>.png plus <theme>_crop.png (1:1 crops of the left and right label columns).
"""
import json
import os
import pickle
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("CABLEBENCH_DEVICE", "GPU")
from cablebench import bl  # noqa: E402
from cablebench.render import build, ground_truth  # noqa: E402
from cablebench.themes import THEMES  # noqa: E402
from PIL import Image  # noqa: E402

pkl, out = sys.argv[1], sys.argv[2]
ls = float(sys.argv[3]) if len(sys.argv) > 3 else 1.4
os.makedirs(out, exist_ok=True)
for t in ["railway", "scifi", "steampunk", "synth", "security"]:
    d = pickle.load(open(pkl, "rb"))
    pz = d["puzzle"]
    n = len(pz.left_labels)
    pz.right_labels = [str(100 + i) for i in range(n)]
    if t == "railway":
        pz.left_labels = [f"LINE {i}" for i in range(n)]
    build(pz, THEMES[t], np.random.default_rng(1), res=(3840, 2160), samples=32, label_scale=ls)
    img = os.path.join(out, f"{t}.png")
    bl.render(img)
    _, lp, rp = ground_truth(pz, THEMES[t])
    im = Image.open(img).convert("RGB")
    y = int(lp[n // 2][1])
    a = im.crop((max(0, int(lp[0][0]) - 320), y - 160, int(lp[0][0]) + 120, y + 160))
    y = int(rp[n // 2][1])
    b = im.crop((int(rp[0][0]) - 120, y - 160, min(im.width, int(rp[0][0]) + 320), y + 160))
    c = Image.new("RGB", (880, 320))
    c.paste(a, (0, 0))
    c.paste(b, (440, 0))
    c.save(os.path.join(out, f"{t}_crop.png"))
    print(t, "done", flush=True)
