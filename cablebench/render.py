"""Scene assembly: puzzle + theme -> rendered image + ground truth."""
from __future__ import annotations

import json
import math
import os
import time

import numpy as np

from . import bl
from .puzzle import generate, PuzzleConfig


def cable_colors(theme, rng, n, mode):
    pal = theme.palette
    if mode == "uniform":
        return [pal[0]] * n
    if mode == "few":
        k = min(len(pal), int(rng.integers(2, 4)))
        return [pal[int(rng.integers(k))] for _ in range(n)]
    if mode == "unique":
        import colorsys
        hs = rng.permutation(n) / n
        return [colorsys.hsv_to_rgb(h, 0.55, 0.55) for h in hs]
    raise ValueError(mode)


def fit_camera(bounds, res, rng, tilt_deg=(4, 12), yaw_deg=2.0, lens=50, margin=1.02, z0=0.0):
    x0, x1, y0, y1 = bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = x1 - x0, y1 - y0
    aspect = res[0] / res[1]
    fov_h = 2 * math.atan(18 / lens)
    fov_v = 2 * math.atan(18 / aspect / lens)
    dist = max(w / 2 / math.tan(fov_h / 2), h / 2 / math.tan(fov_v / 2)) * margin
    tilt = math.radians(rng.uniform(*tilt_deg))
    yaw = math.radians(rng.uniform(-yaw_deg, yaw_deg))
    loc = (cx + dist * math.sin(yaw), cy - dist * math.sin(tilt), z0 + dist * math.cos(tilt))
    return bl.camera(loc, (cx, cy, z0), lens=lens)


def build(pz, theme, rng, color_mode="uniform", res=(1600, 900), samples=48, extras=True, label_scale=1.0):
    bl.reset()
    n = len(pz.cables)
    r = pz.config["cable_radius"]
    ctx = dict(W=pz.W, H=pz.H, r=r, n=n, pitch=pz.config["pitch"], rng=rng, label_scale=label_scale)
    bounds = theme.build(pz, ctx)
    cols = cable_colors(theme, rng, n, color_mode)
    mats = {}
    for i, c in enumerate(pz.cables):
        key = tuple(np.round(cols[i], 3))
        if key not in mats:
            mats[key] = theme.cable_material(cols[i], ctx)
        P = np.array(c)
        P[:, 2] += theme.cable_z0
        bl.tube(f"cable_{i}", P, r * theme.radius_scale, ring=16, mat=mats[key])
    for i, c in enumerate(getattr(pz, "loose", []) or []):
        key = tuple(np.round(cols[i % n], 3))
        if key not in mats:
            mats[key] = theme.cable_material(cols[i % n], ctx)
        P = np.array(c)
        P[:, 2] += theme.cable_z0
        bl.tube(f"loose_{i}", P, r * theme.radius_scale, ring=16, mat=mats[key])
    if extras:
        theme.extras(pz, ctx)
    cam = fit_camera(bounds, res, rng, **theme.camera_kw)
    theme.lights(bounds, ctx)
    bl.setup_render(res=res, samples=samples, exposure=theme.exposure)
    return cam, ctx


def ground_truth(pz, theme):
    """Projected cable centrelines and port positions in pixel coordinates."""
    out = {}
    for i, c in enumerate(pz.cables):
        P = np.array(c)[::6].copy()
        P[:, 2] += theme.cable_z0
        out[i] = [[round(x, 1), round(y, 1)] for x, y, _ in bl.project(P)]
    lp = bl.project([(x, y, theme.cable_z0 + pz.config["cable_radius"]) for x, y in pz.left_ports])
    rp = bl.project([(x, y, theme.cable_z0 + pz.config["cable_radius"]) for x, y in pz.right_ports])
    return out, [[round(a, 1), round(b, 1)] for a, b, _ in lp], [[round(a, 1), round(b, 1)] for a, b, _ in rp]


def make_one(out_dir, name, theme, pcfg: PuzzleConfig, color_mode="uniform", res=(1600, 900),
             samples=48, seed=0, extras=True):
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed + 7919)
    for k, v in theme.puzzle_overrides.items():
        setattr(pcfg, k, v)
    t0 = time.time()
    pz = generate(pcfg)
    t1 = time.time()
    _, ctx = build(pz, theme, rng, color_mode=color_mode, res=res, samples=samples, extras=extras)
    img = os.path.join(out_dir, name + ".png")
    bl.render(img)
    t2 = time.time()
    paths, lp, rp = ground_truth(pz, theme)
    meta = dict(
        image=os.path.basename(img), theme=theme.name, color_mode=color_mode,
        resolution=list(res), seed=seed,
        left_labels=pz.left_labels, right_labels=pz.right_labels,
        solution=pz.solution(),
        stats=pz.stats, notes=ctx.get("notes", {}),
        timing=dict(puzzle_s=round(t1 - t0, 2), render_s=round(t2 - t1, 2)),
        left_ports_px=lp, right_ports_px=rp, cable_paths_px=paths,
        puzzle=pz.to_json(),
    )
    with open(os.path.join(out_dir, name + ".json"), "w") as f:
        json.dump(meta, f)
    return img, meta


def overlay(img_path, meta, out_path):
    """Debug image: draw ground-truth centrelines on top of the render."""
    from PIL import Image, ImageDraw
    import colorsys
    im = Image.open(img_path).convert("RGB")
    dr = ImageDraw.Draw(im)
    paths = meta["cable_paths_px"]
    n = len(paths)
    for i in range(n):
        pts = [tuple(p) for p in paths[str(i) if str(i) in paths else i]]
        col = tuple(int(255 * c) for c in colorsys.hsv_to_rgb(i / n, 1, 1))
        dr.line(pts, fill=col, width=3)
        dr.text((pts[0][0] + 6, pts[0][1] - 14), meta["left_labels"][i], fill=col)
        j = meta["puzzle"]["perm"][i]
        dr.text((pts[-1][0] - 30, pts[-1][1] - 14), meta["right_labels"][j], fill=col)
    im.save(out_path)
