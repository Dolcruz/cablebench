#!/usr/bin/env python3
"""Visual check of a generated grid: one sheet per item with the whole image (scaled) and 1:1 crops of
the left and right label columns (top, middle, bottom), plus label height in pixels.

  python bench/contact_sheet.py --grid pilot --out <folder> [--ids g_calm_n100_00,...]
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

DATA = os.path.join(os.path.expanduser("~"), "cablebench-data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="pilot")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    gd = os.path.join(a.data, a.grid)
    os.makedirs(a.out, exist_ok=True)
    for line in open(os.path.join(gd, "manifest.jsonl")):
        r = json.loads(line)
        if a.ids and r["id"] not in a.ids.split(","):
            continue
        m = json.load(open(os.path.join(gd, "meta", r["id"] + ".json")))
        im = Image.open(os.path.join(gd, r["image"])).convert("RGB")
        W, H = im.size
        lp, rp = m["left_ports_px"], m["right_ports_px"]
        n = len(lp)
        pitch = abs(lp[-1][1] - lp[0][1]) / max(1, n - 1)
        crops = []
        for k in (0, n // 2, n - 1):
            y = int(lp[k][1])
            x = int(lp[k][0])
            crops.append(im.crop((max(0, x - 330), y - 90, x + 70, y + 90)))
            y = int(rp[k][1])
            x = int(rp[k][0])
            crops.append(im.crop((x - 70, y - 90, min(W, x + 330), y + 90)))
        sw = 1600
        full = im.resize((sw, int(H * sw / W)))
        sheet = Image.new("RGB", (sw, full.height + 3 * 180 + 30), (20, 20, 20))
        sheet.paste(full, (0, 30))
        for j, c in enumerate(crops):
            sheet.paste(c, ((j % 2) * 800, full.height + 30 + (j // 2) * 180))
        d = ImageDraw.Draw(sheet)
        d.text((8, 8), f"{r['id']}  {r['theme']}  n={n}  {W}x{H}  port pitch {pitch:.1f}px  label_scale {r.get('label_scale')}  "
                       f"crossings {r['n_crossings']}  min angle {r.get('min_cross_angle_deg')}  bundles {r.get('bundles')}  "
                       f"loose {r.get('n_loose')}", fill=(255, 255, 0))
        sheet.save(os.path.join(a.out, r["id"] + ".jpg"), quality=88)
        print(r["id"], f"pitch {pitch:.1f}px")


if __name__ == "__main__":
    main()
