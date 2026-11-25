"""Visual themes. Same game, different looks.

Every theme builds: a board, a labelled port column on the left (x = 0),
a labelled connector column on the right (x = W), decoration and lights.
The cables themselves are added by render.build() with the theme's material.
"""
from __future__ import annotations

import math

import numpy as np

from . import bl


# ----------------------------------------------------------------------------
# shared material recipes
# ----------------------------------------------------------------------------

def LS(ctx):
    """Size of labels and label furniture. 1.0 * min(pitch, 1) unless the generator asks for bigger labels
    (ctx["label_scale"], used for >= 70 cables where 4K text would otherwise be ~8 px high)."""
    return min(ctx["pitch"], 1.0) * ctx.get("label_scale", 1.0)

def painted_wood(name, base, dark, scale=1.0):
    nt = bl.NT(name)
    tc = nt.texcoord()
    v = nt.mapping(tc.outputs["Object"], scale=(0.15 * scale, 1.2 * scale, 1))
    grain = nt.noise(v, scale=6, detail=8, rough=0.6, dist=2.0)
    blot = nt.noise(tc.outputs["Object"], scale=0.35 * scale, detail=4)
    r1 = nt.ramp(grain.outputs["Fac"], [(0.35, dark), (0.65, base)])
    r2 = nt.ramp(blot.outputs["Fac"], [(0.3, (0, 0, 0)), (0.7, (1, 1, 1))])
    col = nt.mix(r2.outputs[0], r1.outputs[0], tuple(min(1, c * 1.15) for c in base), "MIX")
    scratch = nt.noise(nt.mapping(tc.outputs["Object"], scale=(8, 0.4, 1)), scale=12, detail=2)
    rough = nt.ramp(scratch.outputs["Fac"], [(0.45, (0.85, 0.85, 0.85)), (0.6, (0.55, 0.55, 0.55))])
    nt.principled(**{"Base Color": col, "Roughness": rough.outputs[0],
                     "Normal": nt.bump(grain.outputs["Fac"], 0.15)})
    return nt.mat


def worn_metal(name, base=(0.09, 0.09, 0.1), rough=(0.35, 0.65), metal=0.85, rust=None, scale=1.0, rust_amt=0.58):
    nt = bl.NT(name)
    tc = nt.texcoord()
    o = tc.outputs["Object"]
    n1 = nt.noise(o, scale=3 * scale, detail=10, rough=0.65)
    scr = nt.noise(nt.mapping(o, scale=(14 * scale, 0.8 * scale, 1), rot=(0, 0, 0.5)), scale=10, detail=3)
    col = nt.ramp(n1.outputs["Fac"], [(0.3, tuple(c * 0.6 for c in base)), (0.7, tuple(min(1, c * 1.6) for c in base))]).outputs[0]
    rough_out = nt.ramp(scr.outputs["Fac"], [(0.4, (rough[1],) * 3), (0.62, (rough[0],) * 3)]).outputs[0]
    metal_v = metal
    if rust is not None:
        rn = nt.noise(o, scale=1.5 * scale, detail=8, rough=0.7)
        rm = nt.ramp(rn.outputs["Fac"], [(rust_amt, (0, 0, 0)), (rust_amt + 0.14, (1, 1, 1))])
        col = nt.mix(rm.outputs[0], col, rust)
        rough_out = nt.mix(rm.outputs[0], rough_out, (0.9, 0.9, 0.9))
        metal_v = nt.math("MULTIPLY", nt.math("SUBTRACT", 1.0, rm.outputs[0]), metal)
    nt.principled(**{"Base Color": col, "Roughness": rough_out, "Metallic": metal_v,
                     "Normal": nt.bump(n1.outputs["Fac"], 0.12)})
    return nt.mat


def plastic(name, color, rough=0.35, coat=0.3, bump=0.03):
    nt = bl.NT(name)
    tc = nt.texcoord()
    nz = nt.noise(tc.outputs["Object"], scale=60, detail=2)
    nt.principled(**{"Base Color": color, "Roughness": rough, "Coat": coat,
                     "Normal": nt.bump(nz.outputs["Fac"], bump)})
    return nt.mat


def brass(name, base=(0.78, 0.56, 0.24), rough=(0.25, 0.5), patina=None):
    return worn_metal(name, base, rough=rough, metal=1.0, rust=patina, scale=2.0, rust_amt=0.6)


def backdrop(bounds, color, z=-0.6, scale=0.4):
    x0, x1, y0, y1 = bounds
    s = max(x1 - x0, y1 - y0)
    nt = bl.NT("backdrop")
    tc = nt.texcoord()
    nz = nt.noise(tc.outputs["Object"], scale=scale, detail=3)
    c = nt.ramp(nz.outputs["Fac"], [(0.3, tuple(v * 0.5 for v in color)), (0.7, color)])
    nt.principled(**{"Base Color": c.outputs[0], "Roughness": 0.9})
    bl.box("backdrop", ((x0 + x1) / 2, (y0 + y1) / 2, z - 0.05), (3 * s, 3 * s, 0.1), nt.mat)


# ----------------------------------------------------------------------------
# icons
# ----------------------------------------------------------------------------
def _ngon(k, R, phase=math.pi / 2):
    a = phase + np.arange(k) * 2 * math.pi / k
    return np.column_stack([R * np.cos(a), R * np.sin(a)])


def symbol_icon(name, kind, center, size, z0, z1, mat):
    cx, cy = center
    R = size / 2
    if kind in ("circle", "dot"):
        P = _ngon(40, R * (0.45 if kind == "dot" else 1.0))
    elif kind == "ring":
        ob = bl.torus(name, (cx, cy, (z0 + z1) / 2), R * 0.78, R * 0.2, mat=mat)
        ob.scale = (1, 1, max(0.3, (z1 - z0) / (R * 0.4)))
        return ob
    elif kind == "square":
        P = _ngon(4, R * 1.2, math.pi / 4)
    elif kind == "diamond":
        P = _ngon(4, R * 1.15) * [0.85, 1.0]
    elif kind == "triangle":
        P = _ngon(3, R * 1.15) + [0, -0.12 * R]
    elif kind == "hexagon":
        P = _ngon(6, R * 1.05, 0)
    elif kind == "pentagon":
        P = _ngon(5, R * 1.08)
    elif kind == "star":
        o = _ngon(4, R * 1.15); i = _ngon(4, R * 0.32, math.pi / 2 + math.pi / 4)
        P = np.vstack([v for pair in zip(o, i) for v in pair])
    elif kind == "cross":
        a, b = R, R * 0.33
        P = np.array([(-b, a), (b, a), (b, b), (a, b), (a, -b), (b, -b), (b, -a), (-b, -a), (-b, -b), (-a, -b), (-a, b), (-b, b)])
    elif kind == "bar":
        P = np.array([(-R, -R * 0.3), (R, -R * 0.3), (R, R * 0.3), (-R, R * 0.3)])
    elif kind == "chevron":
        P = np.array([(-R, R * 0.2), (0, -R * 0.6), (R, R * 0.2), (R, R * 0.7), (0, -R * 0.1), (-R, R * 0.7)])
    else:
        raise ValueError(kind)
    return bl.poly_prism(name, P + [cx, cy], z0, z1, mat=mat)


WAVES = ["sine", "square", "saw", "triangle", "noise", "pulse", "steps", "ramp_down"]


def wave_icon(name, kind, center, size, z, mat, rng, thick=0.025):
    cx, cy = center
    w, h = size * 1.3, size * 0.55
    t = np.linspace(0, 1, 160)
    if kind == "sine":
        y = np.sin(2 * math.pi * 1.25 * t)
    elif kind == "square":
        y = np.tanh(8 * np.sin(2 * math.pi * 1.5 * t + 1e-3))
    elif kind == "saw":
        y = 2 * ((1.5 * t) % 1) - 1
    elif kind == "triangle":
        y = 2 * np.abs(2 * ((1.5 * t + 0.25) % 1) - 1) - 1
    elif kind == "noise":
        y = np.interp(t, np.linspace(0, 1, 14), rng.uniform(-1, 1, 14))
    elif kind == "pulse":
        y = np.tanh(10 * (np.where((3 * t) % 1 < 0.25, 1.0, -1.0)))
    elif kind == "steps":
        y = np.floor(t * 5) / 2.5 - 0.9
    elif kind == "ramp_down":
        y = 1 - 2 * ((1.5 * t) % 1)
    else:
        raise ValueError(kind)
    P = np.column_stack([cx - w / 2 + w * t, cy + h / 2 * y, np.full_like(t, z)])
    return bl.tube(name, P, thick, ring=8, mat=mat)


# ----------------------------------------------------------------------------
# extras shared by several themes
# ----------------------------------------------------------------------------
def free_spots(pz, ctx, k, min_gap_r=5.0, rng=None):
    """Pick k (cable, index) positions lying flat, away from crossings, ports and neighbours."""
    rng = rng or ctx["rng"]
    r, W = ctx["r"], ctx["W"]
    cross = np.array([x["point"] for x in pz.crossings]) if pz.crossings else np.zeros((0, 2))
    allp = [np.array(c) for c in pz.cables]
    out = []
    tries = 0
    while len(out) < k and tries < 400:
        tries += 1
        i = int(rng.integers(len(allp)))
        P = allp[i]
        j = int(rng.integers(len(P) // 10, len(P) * 9 // 10))
        x, y, z = P[j]
        if z > r * 1.05 or x < 1.2 or x > W - 1.2:
            continue
        if len(cross) and np.min(np.linalg.norm(cross - [x, y], axis=1)) < min_gap_r * r:
            continue
        ok = True
        for q, Q in enumerate(allp):
            if q == i:
                continue
            if np.min(np.linalg.norm(Q[::4, :2] - [x, y], axis=1)) < 3.2 * r:
                ok = False
                break
        for (_, _, ox, oy) in out:
            if math.hypot(ox - x, oy - y) < 1.5:
                ok = False
        if not ok:
            continue
        out.append((i, j, x, y))
    return out


def add_clips(pz, ctx, k, mat, screw_mat=None, width=1.0, style="strap"):
    r = ctx["r"]
    for c, (i, j, x, y) in enumerate(free_spots(pz, ctx, k)):
        P = np.array(pz.cables[i])
        t = P[min(j + 2, len(P) - 1), :2] - P[max(j - 2, 0), :2]
        t /= np.linalg.norm(t)
        nrm = np.array([-t[1], t[0]])
        R = 1.35 * r
        th = np.linspace(0, math.pi, 24)
        arc = [(x + nrm[0] * R * math.cos(a), y + nrm[1] * R * math.cos(a), r + R * math.sin(a) * 0.95) for a in th]
        feet0 = (x + nrm[0] * (R + 0.6 * r), y + nrm[1] * (R + 0.6 * r), 0.03)
        feet1 = (x - nrm[0] * (R + 0.6 * r), y - nrm[1] * (R + 0.6 * r), 0.03)
        pts = [feet0, (x + nrm[0] * R, y + nrm[1] * R, 0.04)] + arc[1:-1] + [(x - nrm[0] * R, y - nrm[1] * R, 0.04), feet1]
        if style == "strap":
            for o in np.linspace(-0.6, 0.6, 3) * r * width:
                pp = [(px + t[0] * o, py + t[1] * o, pz_) for px, py, pz_ in pts]
                bl.tube(f"clip_{c}_{o:.3f}", pp, 0.28 * r, ring=8, mat=mat)
        else:
            bl.tube(f"clip_{c}", pts, 0.32 * r, ring=10, mat=mat)
        if screw_mat is not None:
            for s, f in enumerate((feet0, feet1)):
                bl.cylinder(f"clipscrew_{c}_{s}", (f[0], f[1], 0.05), 0.25 * r, 0.04, mat=screw_mat)


def pliers_geometry(center, angle, scale):
    cx, cy = center
    ca, sa = math.cos(angle), math.sin(angle)

    def tr(px, py):
        return (cx + scale * (px * ca - py * sa), cy + scale * (px * sa + py * ca))

    parts = []
    for side in (1, -1):
        parts.append(("h", [tr(0.15, 0.03 * side), tr(0.6, 0.16 * side), tr(1.1, 0.26 * side), tr(1.6, 0.30 * side)], 0.075 * scale))
        parts.append(("j", [tr(-0.45, 0.0), tr(-0.2, 0.07 * side), tr(0.15, 0.05 * side)], 0.06 * scale))
    parts.append(("p", [tr(0.0, 0.0), tr(0.0001, 0.0)], 0.09 * scale))
    return parts


def _capsule_dist(P, poly):
    """Distance from points P (n,2) to polyline poly."""
    Q = np.asarray(poly, float)
    d = np.full(len(P), np.inf)
    for a, b in zip(Q[:-1], Q[1:]):
        ab = b - a
        t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        d = np.minimum(d, np.linalg.norm(P - (a + t[:, None] * ab), axis=1))
    return d


def occluder_ok(pz, ctx, parts, max_hidden_r=7.0, cross_margin_r=4.0):
    """Fairness check: every hidden stretch is short and contains no crossing."""
    r = ctx["r"]
    cross = np.array([x["point"] for x in pz.crossings]) if pz.crossings else np.zeros((0, 2))
    hidden_total = 0.0
    for poly, rad in [(p[1], p[2]) for p in parts]:
        if len(cross) and np.min(_capsule_dist(cross, poly)) < rad + cross_margin_r * r:
            return False, 0.0
    loose = getattr(pz, "loose", []) or []
    for c in loose:  # never hide the end of a distractor piece
        E = np.array(c)[[0, -1], :2]
        for poly, rad in [(p[1], p[2]) for p in parts]:
            if np.min(_capsule_dist(E, poly)) < rad + 4 * r:
                return False, 0.0
    for c in list(pz.cables) + list(loose):
        P = np.array(c)[:, :2]
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        hid = np.zeros(len(P), bool)
        for _, poly, rad in parts:
            hid |= _capsule_dist(P, poly) < rad + 1.2 * r
        if not hid.any():
            continue
        # contiguous runs
        edges = np.flatnonzero(np.diff(np.concatenate([[0], hid.astype(int), [0]])))
        for a, b in zip(edges[::2], edges[1::2]):
            L = s[b - 1] - s[a]
            if L > max_hidden_r * r:
                return False, 0.0
            hidden_total += L
    return True, hidden_total


def place_pliers(pz, ctx, handle_mat, metal_mat, scale=1.6, z=0.5, tries=80):
    rng = ctx["rng"]
    W = ctx["W"]
    ys = [p[1] for p in pz.left_ports]
    for _ in range(tries):
        c = (rng.uniform(1.0, W - 1.0), float(rng.uniform(min(ys), max(ys))))
        ang = rng.uniform(-math.pi, math.pi)
        parts = pliers_geometry(c, ang, scale)
        xs_all = [x for _, poly, _ in parts for x, _ in poly]
        if min(xs_all) < 0.7 or max(xs_all) > W - 0.7:
            continue  # keep labels, ports and connectors visible
        ok, hidden = occluder_ok(pz, ctx, parts)
        if ok and hidden > 0:
            for k, (kind, poly, rad) in enumerate(parts):
                if kind == "p":
                    bl.cylinder(f"pl_pivot", (poly[0][0], poly[0][1], z + 0.02 * scale), rad, 0.1 * scale, mat=metal_mat)
                else:
                    bl.tube(f"pl_{kind}{k}", [(x, y, z) for x, y in poly], rad, ring=12,
                            mat=handle_mat if kind == "h" else metal_mat)
            ctx.setdefault("notes", {})["occluder"] = dict(kind="pliers", center=list(c), angle=round(ang, 3),
                                                            hidden_cable_length=round(hidden, 3))
            return True
    return False


# ----------------------------------------------------------------------------
# cable materials
# ----------------------------------------------------------------------------
def rubber_cable(color, name="cable_rubber", contrast=0.12, rough=(0.5, 0.32), coat=0.15):
    nt = bl.NT(name)
    tc = nt.texcoord()
    o = tc.outputs["Object"]
    dirt = nt.noise(o, scale=5, detail=5)
    fine = nt.noise(o, scale=90, detail=3)
    c = nt.ramp(dirt.outputs["Fac"], [(0.3, tuple(x * (1 - contrast) for x in color)),
                                      (0.7, tuple(min(1, x * (1 + contrast)) for x in color))])
    rr = nt.ramp(dirt.outputs["Fac"], [(0.3, (rough[0],) * 3), (0.75, (rough[1],) * 3)])
    nt.principled(**{"Base Color": c.outputs[0], "Roughness": rr.outputs[0], "Specular": 0.55,
                     "Coat": coat, "Normal": nt.bump(fine.outputs["Fac"], 0.05)})
    return nt.mat


def braided_cable(color, stripe=(0.85, 0.8, 0.6), name="cable_braid"):
    """Textile braid: helical stripes from the tube UVs (u along, v around)."""
    nt = bl.NT(name)
    tc = nt.texcoord()
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.link(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    ph = nt.math("ADD", nt.math("MULTIPLY", u, 1.6), v)
    ph2 = nt.math("SUBTRACT", nt.math("MULTIPLY", u, 1.6), v)
    s1 = nt.math("SINE", nt.math("MULTIPLY", ph, 2 * math.pi * 2))
    s2 = nt.math("SINE", nt.math("MULTIPLY", ph2, 2 * math.pi * 9))
    stripe_mask = nt.ramp(s1, [(0.55, (0, 0, 0)), (0.75, (1, 1, 1))]).outputs[0]
    weave = nt.math("MULTIPLY", s2, 0.5)
    col = nt.mix(stripe_mask, color, stripe)
    dirt = nt.noise(tc.outputs["Object"], scale=4, detail=4)
    dm = nt.ramp(dirt.outputs["Fac"], [(0.3, (0.75, 0.75, 0.75)), (0.7, (1, 1, 1))]).outputs[0]
    col = nt.mix(1.0, col, dm, "MULTIPLY")
    nt.principled(**{"Base Color": col, "Roughness": 0.75, "Sheen": 0.4,
                     "Normal": nt.bump(nt.math("ADD", weave, nt.math("MULTIPLY", s1, 0.3)), 0.35, 0.01)})
    return nt.mat


# ----------------------------------------------------------------------------
# theme base
# ----------------------------------------------------------------------------
class Theme:
    name = "base"
    palette = [(0.3, 0.5, 0.25)]
    radius_scale = 1.0
    cable_z0 = 0.0
    exposure = 0.0
    camera_kw = {}
    puzzle_overrides = {}
    clips = (0, 0)

    def build(self, pz, ctx):
        raise NotImplementedError

    def cable_material(self, color, ctx):
        return rubber_cable(color)

    def extras(self, pz, ctx):
        pass

    def lights(self, bounds, ctx):
        pass

    @staticmethod
    def light_scale(bounds):
        x0, x1, y0, y1 = bounds
        s = max(x1 - x0, y1 - y0)
        return (x0 + x1) / 2, (y0 + y1) / 2, s, (s / 15) ** 2


# ----------------------------------------------------------------------------
# 1) bomb defusal panel (olive board, steel plate, green cables, LEDs, timer)
# ----------------------------------------------------------------------------
class Bomb(Theme):
    name = "bomb"
    palette = [(0.36, 0.62, 0.28), (0.78, 0.62, 0.18), (0.06, 0.06, 0.06), (0.60, 0.13, 0.10)]
    camera_kw = dict(tilt_deg=(3, 10), lens=50)
    puzzle_overrides = dict(left_label_style="letters", right_label_style="numbers")

    def cable_material(self, color, ctx):
        return rubber_cable(color, contrast=0.08)

    def build(self, pz, ctx):
        W, H, r, n, pitch, rng = ctx["W"], ctx["H"], ctx["r"], ctx["n"], ctx["pitch"], ctx["rng"]
        top = H / 2 + 0.6 * pitch
        bot = -H / 2 - 0.6 * pitch
        x0, x1 = -1.9, W + 2.0
        y0, y1 = bot - 0.7, top + 1.9
        board = painted_wood("board", (0.25, 0.23, 0.14), (0.14, 0.13, 0.08), scale=1 / max(1, W / 12))
        bl.box("board", ((x0 + x1) / 2, (y0 + y1) / 2, -0.1), (x1 - x0, y1 - y0, 0.2), board, bevel=0.02)
        steel = worn_metal("steel", (0.10, 0.10, 0.11), rust=(0.16, 0.10, 0.06))
        bl.box("plate", (-0.85, (top + bot) / 2, 0.025), (1.55, top - bot + 0.5, 0.05), steel, bevel=0.01)
        paint = bl.simple_mat("paint", (0.85, 0.83, 0.75), rough=0.8)
        dark = bl.simple_mat("rubber_dark", (0.03, 0.03, 0.03), rough=0.5)
        chrome = bl.simple_mat("chrome", (0.6, 0.6, 0.62), rough=0.25, metal=1.0)
        ts = 0.42 * LS(ctx)
        for i, (x, y) in enumerate(pz.left_ports):
            bl.torus(f"eyelet_{i}", (x - 0.02, y, 0.06), 1.55 * r, 0.42 * r, mat=chrome)
            bl.cylinder(f"boot_{i}", (x - 0.06, y, r), 1.25 * r, 0.22, axis="X", mat=dark)
            bl.text(f"ll_{i}", pz.left_labels[i], (x - 1.05, y, 0.05), ts, mat=paint, extrude=0.002)
        for k, (sx, sy) in enumerate([(-1.5, top + 0.1), (-0.2, top + 0.1), (-1.5, bot - 0.1), (-0.2, bot - 0.1)]):
            bl.cylinder(f"screw_{k}", (sx, sy, 0.055), 0.06, 0.03, mat=chrome)
        bh = 0.32
        bl.box("block", (W + 0.85, (top + bot) / 2, bh / 2), (1.6, top - bot + 0.4, bh), steel, bevel=0.03)
        led_on = bl.emissive("led_green", (0.02, 1.0, 0.05), 1.6)
        led_off = bl.emissive("led_red", (1.0, 0.0, 0.0), 1.6)
        nut = worn_metal("nut", (0.25, 0.25, 0.26), rough=(0.25, 0.5))
        for j, (x, y) in enumerate(pz.right_ports):
            bl.cylinder(f"nut_{j}", (x - 0.04, y, r), 1.6 * r, 0.16, axis="X", mat=nut, verts=6, bevel=0.01)
            bl.sphere(f"led_{j}", (x + 0.55, y, bh), 0.11 * LS(ctx) / 0.9,
                      mat=led_on if rng.random() < 0.5 else led_off, scale=(1, 1, 0.6))
            bl.text(f"rl_{j}", pz.right_labels[j], (x + 0.55 + 0.13 * LS(ctx) + 0.12, y, bh), ts, mat=paint, extrude=0.002,
                    align="LEFT")
        tw = min(3.2, W * 0.3)
        bl.box("timer", (W + 1.6 - tw / 2, top + 1.0, 0.18), (tw, 1.3, 0.36),
               bl.simple_mat("timer_case", (0.02, 0.02, 0.02), 0.4), bevel=0.04)
        bl.box("timer_glass", (W + 1.6 - tw / 2, top + 1.0, 0.365), (tw - 0.3, 1.0, 0.01), bl.simple_mat("lcd", (0.01, 0.0, 0.0), 0.15))
        mins = int(rng.integers(0, 3)); secs = int(rng.integers(0, 60))
        bl.text("timer_txt", f"{mins:02d}:{secs:02d}", (W + 1.6 - tw / 2, top + 1.0, 0.372), 0.7,
                mat=bl.emissive("seg", (1.0, 0.02, 0.01), 2.5), extrude=0.0)
        bl.tube("timer_wire", [(W + 1.6 - tw + 0.2, top + 0.6, 0.2), (W + 0.5, top + 0.3, 0.35), (W + 0.4, top - 0.1, bh)],
                0.03, mat=dark)
        yel = rubber_cable((0.75, 0.6, 0.2), "jumper")
        for i, (x, y) in enumerate(pz.left_ports):
            bl.torus(f"eyelet2_{i}", (-0.62, y, 0.06), 1.3 * r, 0.38 * r, mat=chrome)
            if rng.random() < 0.6:
                bl.tube(f"jump_{i}", [(-0.62, y, 0.06), (-0.55, y, 0.13), (-0.08, y, 0.13), (0.0, y, 0.06)], 0.55 * r, mat=yel)
        return (x0 + 0.1, x1 - 0.1, y0 + 0.1, y1 - 0.1)

    def extras(self, pz, ctx):
        rng = ctx["rng"]
        if rng.random() < 0.5:
            blue = plastic("pl_handle", (0.08, 0.12, 0.35), rough=0.5)
            steel = bl.simple_mat("pl_steel", (0.5, 0.5, 0.52), rough=0.35, metal=1.0)
            place_pliers(pz, ctx, blue, steel)

    def lights(self, bounds, ctx):
        cx, cy, s, k = self.light_scale(bounds)
        x0, x1, y0, y1 = bounds
        bl.area_light("key", (x0 - 0.1 * s, y1 + 0.45 * s, 0.75 * s), (cx, cy, 0), 2000 * k, 0.25 * s, (1.0, 0.92, 0.80))
        bl.area_light("fill", (x1 + 0.3 * s, y0 - 0.3 * s, 0.9 * s), (cx, cy, 0), 350 * k, 0.9 * s, (0.70, 0.82, 1.0))
        bl.area_light("top", (cx, cy, 1.3 * s), (cx, cy, 0), 300 * k, 0.6 * s, (1, 1, 1))
        backdrop(bounds, (0.035, 0.04, 0.045))
        bl.world((0.02, 0.025, 0.03), 0.5)


# ----------------------------------------------------------------------------
# 2) railway signal box (brass name plates, braided cables, semaphore flags)
# ----------------------------------------------------------------------------
class Railway(Theme):
    name = "railway"
    palette = [(0.72, 0.50, 0.12), (0.25, 0.45, 0.22), (0.30, 0.36, 0.45)]
    camera_kw = dict(tilt_deg=(4, 12), lens=50)
    puzzle_overrides = dict(left_label_style="words", right_label_style="numbers")
    clips = (2, 5)

    def cable_material(self, color, ctx):
        return braided_cable(color, stripe=(0.82, 0.78, 0.6))

    def build(self, pz, ctx):
        W, H, r, n, pitch, rng = ctx["W"], ctx["H"], ctx["r"], ctx["n"], ctx["pitch"], ctx["rng"]
        top = H / 2 + 0.6 * pitch
        bot = -H / 2 - 0.6 * pitch
        ts = 0.3 * LS(ctx)
        maxlen = max(len(s) for s in pz.left_labels)
        pw = max(1.0, 0.21 * maxlen * ts / 0.3 + 0.35)
        px = -1.45 - pw / 2
        x0, x1 = px - pw / 2 - 0.4, W + 2.6
        y0, y1 = bot - 0.8, top + 0.8
        board = worn_metal("board", (0.16, 0.17, 0.10), rough=(0.55, 0.8), metal=0.15, rust=(0.22, 0.12, 0.05), scale=0.5)
        bl.box("board", ((x0 + x1) / 2, (y0 + y1) / 2, -0.1), (x1 - x0, y1 - y0, 0.2), board, bevel=0.06)
        iron = worn_metal("iron", (0.06, 0.06, 0.06), rough=(0.5, 0.75), metal=0.6, rust=(0.2, 0.1, 0.05))
        bl.box("leftpanel", ((x0 + 0.2) / 2, (top + bot) / 2, 0.02), (0.2 - x0 - 0.2, top - bot + 0.6, 0.04), iron, bevel=0.02)
        br = brass("brass", patina=(0.25, 0.32, 0.22))
        plate_m = brass("plate_brass", (0.55, 0.40, 0.18), rough=(0.45, 0.7))
        engrave = bl.simple_mat("engrave", (0.01, 0.008, 0.005), rough=0.8)
        braid = braided_cable((0.85, 0.8, 0.62), stripe=(0.55, 0.5, 0.38), name="jumper_braid")
        for i, (x, y) in enumerate(pz.left_ports):
            bl.box(f"plate_{i}", (px, y, 0.06), (pw, 0.52 * LS(ctx), 0.04), plate_m, bevel=0.015)
            bl.text(f"ll_{i}", pz.left_labels[i], (px, y, 0.082), ts, mat=engrave, extrude=0.004)
            bl.torus(f"ring_a_{i}", (-1.2, y, 0.06), 1.4 * r, 0.45 * r, mat=br)
            bl.torus(f"ring_b_{i}", (x - 0.05, y, 0.06), 1.5 * r, 0.5 * r, mat=br)
            bl.tube(f"jump_{i}", [(-1.2, y, 0.08), (-1.0, y, 0.11), (-0.3, y, 0.11), (x - 0.05, y, 0.08)], 0.75 * r, ring=12, mat=braid)
        case = worn_metal("case", (0.07, 0.06, 0.05), rough=(0.4, 0.7), metal=0.7, rust=(0.25, 0.12, 0.05))
        bl.box("case", (W + 1.35, (top + bot) / 2, 0.2), (2.4, top - bot + 0.5, 0.4), case, bevel=0.05)
        glass = bl.NT("glass")
        glass.principled(**{"Base Color": (0.8, 0.85, 0.9), "Roughness": 0.05, "Transmission": 1.0, "IOR": 1.45})
        cream = bl.simple_mat("flag_cream", (0.85, 0.8, 0.65), rough=0.6)
        red = bl.simple_mat("flag_red", (0.6, 0.05, 0.03), rough=0.55)
        knurl = brass("knurl", (0.55, 0.38, 0.18), rough=(0.35, 0.6))
        for j, (x, y) in enumerate(pz.right_ports):
            bl.cylinder(f"nut_{j}", (x - 0.02, y, r), 1.7 * r, 0.22, axis="X", mat=knurl, verts=16, bevel=0.01)
            pw = max(0.42, 0.2 * len(pz.right_labels[j]) + 0.06) * LS(ctx)
            pcx = x + 0.19 + pw / 2
            hub = (x + 0.19 + pw + 0.3, y, 0.42)
            bl.cylinder(f"hub_{j}", hub, 0.09, 0.06, mat=br)
            ang = rng.uniform(-0.35, 0.35)
            fl = bl.box(f"flag_{j}", (0, 0, 0.43), (0.8, 0.22 * LS(ctx), 0.02),
                        red if rng.random() < 0.5 else cream, bevel=0.005)
            fl.rotation_euler[2] = ang
            fl.location = (hub[0] + 0.45 * math.cos(ang), y + 0.45 * math.sin(ang), 0.43)
            bl.box(f"rplate_{j}", (pcx, y, 0.41), (pw, 0.42 * LS(ctx), 0.02), plate_m, bevel=0.01)
            bl.text(f"rl_{j}", pz.right_labels[j], (pcx, y, 0.422), 0.3 * LS(ctx), mat=engrave, extrude=0.003)
        for k, xx in enumerate((W * 0.33, W * 0.66)):
            for yy in (top + 0.35, bot - 0.35):
                bl.box(f"brk_{k}_{yy:.1f}", (xx, yy, 0.05), (0.3, 0.5, 0.1), br, bevel=0.03)
        return (x0 + 0.1, x1 - 0.1, y0 + 0.1, y1 - 0.1)

    def extras(self, pz, ctx):
        rng = ctx["rng"]
        cu = brass("copper", (0.72, 0.36, 0.2), rough=(0.3, 0.55))
        add_clips(pz, ctx, int(rng.integers(*self.clips)), cu, screw_mat=cu, style="strap")
        if rng.random() < 0.6:
            blue = plastic("pl_handle", (0.1, 0.18, 0.5), rough=0.45)
            steel = worn_metal("pl_steel", (0.4, 0.4, 0.42), rough=(0.3, 0.5), metal=1.0)
            place_pliers(pz, ctx, blue, steel, scale=1.7, z=0.45)

    def lights(self, bounds, ctx):
        cx, cy, s, k = self.light_scale(bounds)
        x0, x1, y0, y1 = bounds
        # the warm lamp hangs over the cable field, not over the name plates: directly above the
        # top-left plates its hot spot washed out the first labels on large boards
        bl.point_light("lamp", (x0 + 0.32 * s, y1 + 0.05 * s, 0.4 * s), 9000 * k, (1.0, 0.72, 0.42), radius=0.05 * s)
        bl.area_light("window", (x1 + 0.2 * s, y1 + 0.4 * s, 0.8 * s), (cx, cy, 0), 600 * k, 0.8 * s, (0.55, 0.68, 1.0))
        bl.area_light("fill", (cx, y0 - 0.5 * s, 0.8 * s), (cx, cy, 0), 150 * k, 0.8 * s, (0.6, 0.7, 0.9))
        backdrop(bounds, (0.03, 0.035, 0.045))
        bl.world((0.02, 0.025, 0.04), 0.6)


# ----------------------------------------------------------------------------
# 3) sci-fi (white housing, translucent tubes, symbol buttons, light tiles)
# ----------------------------------------------------------------------------
class SciFi(Theme):
    name = "scifi"
    palette = [(0.25, 0.85, 0.85), (0.95, 0.75, 0.3), (0.95, 0.45, 0.45), (0.9, 0.92, 0.95)]
    camera_kw = dict(tilt_deg=(6, 14), lens=55)
    puzzle_overrides = dict(left_label_style="symbols", right_label_style="numbers")
    clips = (2, 5)
    exposure = 0.2

    def cable_material(self, color, ctx):
        nt = bl.NT("tube_glass")
        lay = nt.node("ShaderNodeLayerWeight")
        lay.inputs["Blend"].default_value = 0.35
        glow = nt.ramp(lay.outputs["Facing"], [(0.0, tuple(c * 0.25 for c in color)), (1.0, color)])
        nt.principled(**{"Base Color": color, "Roughness": 0.12, "Transmission": 0.85, "IOR": 1.35,
                         "Coat": 0.6, "Emission": glow.outputs[0], "Emission Strength": 0.9})
        return nt.mat

    def build(self, pz, ctx):
        W, H, r, n, pitch, rng = ctx["W"], ctx["H"], ctx["r"], ctx["n"], ctx["pitch"], ctx["rng"]
        if n > 12:
            pz.left_labels[:] = [str(i + 1) for i in range(n)]
        top = H / 2 + 0.6 * pitch
        bot = -H / 2 - 0.6 * pitch
        x0, x1 = -2.0, W + (4.6 if top - bot > 3.5 else 2.4)
        y0, y1 = bot - 0.9, top + 0.9
        white = plastic("white", (0.82, 0.83, 0.85), rough=0.3, coat=0.5)
        bl.box("housing", ((x0 + x1) / 2, (y0 + y1) / 2, -0.15), (x1 - x0, y1 - y0, 0.4), white, bevel=0.3, segments=6)
        inner = bl.NT("inner")
        tc = inner.texcoord()
        nz = inner.noise(tc.outputs["Object"], scale=300, detail=2)
        inner.principled(**{"Base Color": (0.035, 0.037, 0.04), "Roughness": 0.75, "Normal": inner.bump(nz.outputs["Fac"], 0.2)})
        bl.box("inner", (W / 2 - 0.1, 0, 0.0), (W + 0.9, top - bot + 0.6, 0.12), inner.mat, bevel=0.06, segments=4)
        icon = bl.simple_mat("icon", (0.05, 0.055, 0.06), rough=0.6)   # dark: grey glyphs on white buttons were faint under the key light
        chrome = bl.simple_mat("chrome", (0.75, 0.75, 0.78), rough=0.15, metal=1.0)
        darkring = bl.simple_mat("darkring", (0.05, 0.05, 0.06), rough=0.3, metal=0.6)
        bs = 0.72 * LS(ctx)
        for i, (x, y) in enumerate(pz.left_ports):
            bl.box(f"btn_{i}", (-1.05, y, 0.12), (bs * 1.15, bs * 0.95, 0.16), white, bevel=0.06, segments=4)
            if pz.left_labels[i].isdigit():
                bl.text(f"ll_{i}", pz.left_labels[i], (-1.05, y, 0.212), bs * 0.45, mat=icon, extrude=0.006)   # fully above the button top (0.20)
            else:
                symbol_icon(f"sym_{i}", pz.left_labels[i], (-1.05, y), bs * 0.5, 0.195, 0.215, icon)
            bl.cylinder(f"sock_{i}", (x - 0.12, y, r), 1.5 * r, 0.3, axis="X", mat=darkring, bevel=0.01)
            bl.torus(f"sockring_{i}", (x + 0.03, y, r), 1.5 * r, 0.3 * r, axis="X", mat=chrome)
        bl.box("strip", (W + 0.25, 0, 0.12), (0.5, top - bot + 0.2, 0.2), white, bevel=0.05)
        cyan = bl.emissive("tile_cyan", (0.0, 1.0, 0.85), 1.4)
        red = bl.emissive("tile_red", (1.0, 0.03, 0.02), 1.4)
        numm = bl.simple_mat("num_dark", (0.06, 0.065, 0.07), rough=0.5)
        tile = plastic("tile", (0.9, 0.9, 0.92), rough=0.15, coat=0.8)
        for j, (x, y) in enumerate(pz.right_ports):
            bl.cylinder(f"conn_{j}", (x - 0.02, y, r), 1.45 * r, 0.3, axis="X", mat=chrome, bevel=0.01)
            bl.box(f"tile_{j}", (x + 0.9, y, 0.14), (0.5 * LS(ctx), 0.42 * LS(ctx), 0.08), tile, bevel=0.04)
            bl.box(f"light_{j}", (x + 0.9, y, 0.18), (0.32 * LS(ctx), 0.26 * LS(ctx), 0.02),
                   cyan if rng.random() < 0.5 else red, bevel=0.01)
            bl.text(f"rl_{j}", pz.right_labels[j], (x + 0.9 + 0.25 * LS(ctx) + 0.14, y, 0.05), 0.38 * LS(ctx), mat=numm,
                    extrude=0.01, align="LEFT")
        sx, sy = W + 3.35, top - 1.0
        if top - bot > 3.5:
            bl.box("screen", (sx, sy, 0.1), (1.6, 1.4, 0.14), bl.simple_mat("scr", (0.01, 0.015, 0.02), 0.2), bevel=0.15)
            ret = bl.emissive("reticle", (0.2, 0.9, 1.0), 3)
            for k, rr in enumerate((0.22, 0.4)):
                bl.torus(f"ret_{k}", (sx, sy, 0.18), rr, 0.012, mat=ret)
            bl.sphere("ret_dot", (sx, sy, 0.18), 0.06, mat=bl.emissive("retdot", (1, 0.3, 0.25), 4))
        bar = bl.emissive("bar", (1.0, 0.97, 0.9), 3)
        for xx in (W * 0.25, W * 0.75):
            bl.box(f"bar_{xx:.1f}", (xx, y1 - 0.25, 0.06), (1.4, 0.08, 0.02), bar, bevel=0.01)
        return (x0 + 0.05, x1 - 0.05, y0 + 0.05, y1 - 0.05)

    def extras(self, pz, ctx):
        rng = ctx["rng"]
        clip = plastic("clip_white", (0.85, 0.86, 0.88), rough=0.25, coat=0.6)
        add_clips(pz, ctx, int(rng.integers(*self.clips)), clip, style="strap", width=1.4)

    def lights(self, bounds, ctx):
        cx, cy, s, k = self.light_scale(bounds)
        x0, x1, y0, y1 = bounds
        bl.area_light("soft", (cx - 0.2 * s, y1 + 0.3 * s, 1.0 * s), (cx, cy, 0), 2200 * k, 1.2 * s, (0.95, 0.98, 1.0), shape="RECTANGLE")
        bl.area_light("rim", (x1 + 0.4 * s, cy, 0.5 * s), (cx, cy, 0), 500 * k, 0.5 * s, (0.8, 0.9, 1.0))
        backdrop(bounds, (0.75, 0.77, 0.8), scale=0.2)
        bl.world((0.75, 0.8, 0.88), 0.6)


# ----------------------------------------------------------------------------
# 4) steampunk (verdigris panel, copper pipes, brass collars, gauges)
# ----------------------------------------------------------------------------
class Steampunk(Theme):
    name = "steampunk"
    palette = [(0.75, 0.38, 0.20), (0.78, 0.56, 0.24), (0.55, 0.55, 0.55)]
    camera_kw = dict(tilt_deg=(4, 10), lens=50)
    puzzle_overrides = dict(left_label_style="symbols", right_label_style="numbers", cable_radius=0.13,
                            pitch=1.0, min_bend_radius=3.5)
    clips = (4, 9)

    def cable_material(self, color, ctx):
        nt = bl.NT("copper_pipe")
        tc = nt.texcoord()
        o = tc.outputs["Object"]
        n1 = nt.noise(o, scale=8, detail=8)
        pat = nt.noise(o, scale=2.5, detail=6)
        col = nt.ramp(n1.outputs["Fac"], [(0.3, tuple(c * 0.7 for c in color)), (0.7, tuple(min(1, c * 1.15) for c in color))]).outputs[0]
        pm = nt.ramp(pat.outputs["Fac"], [(0.6, (0, 0, 0)), (0.75, (1, 1, 1))]).outputs[0]
        col = nt.mix(pm, col, (0.25, 0.45, 0.38))
        rough = nt.mix(pm, (0.28, 0.28, 0.28), (0.8, 0.8, 0.8))
        metal = nt.math("SUBTRACT", 1.0, pm)
        nt.principled(**{"Base Color": col, "Roughness": rough, "Metallic": metal,
                         "Normal": nt.bump(n1.outputs["Fac"], 0.08)})
        return nt.mat

    def build(self, pz, ctx):
        W, H, r, n, pitch, rng = ctx["W"], ctx["H"], ctx["r"], ctx["n"], ctx["pitch"], ctx["rng"]
        if n > 12:
            pz.left_labels[:] = [str(i + 1) for i in range(n)]
        top = H / 2 + 0.6 * pitch
        bot = -H / 2 - 0.6 * pitch
        # right column: badge (grows with the label), then the gauge behind it, so the gauge never covers digits
        bw_max = max(0.42, 0.2 * max(len(s) for s in pz.right_labels) + 0.06) * LS(ctx)
        g_off = max(1.35, 0.47 + bw_max + 0.12 + 0.34 * LS(ctx))
        x0, x1 = -2.2, W + max(2.1, g_off + 0.34 * LS(ctx) + 0.35)
        y0, y1 = bot - 0.8, top + 0.8
        panel = worn_metal("panel", (0.10, 0.13, 0.17), rough=(0.5, 0.8), metal=0.5, rust=(0.15, 0.32, 0.28), scale=0.7, rust_amt=0.55)
        bl.box("panel", ((x0 + x1) / 2, (y0 + y1) / 2, -0.1), (x1 - x0, y1 - y0, 0.2), panel, bevel=0.08)
        br = brass("brass", patina=(0.2, 0.33, 0.27))
        for nm, c, sz in [("ft", ((x0 + x1) / 2, y1 - 0.12, 0.04), (x1 - x0, 0.24, 0.08)),
                          ("fb", ((x0 + x1) / 2, y0 + 0.12, 0.04), (x1 - x0, 0.24, 0.08)),
                          ("fl", (x0 + 0.12, (y0 + y1) / 2, 0.04), (0.24, y1 - y0, 0.08)),
                          ("fr", (x1 - 0.12, (y0 + y1) / 2, 0.04), (0.24, y1 - y0, 0.08))]:
            bl.box(nm, c, sz, br, bevel=0.03)
        for xx in (x0 + 0.12, x1 - 0.12):
            for yy in (y0 + 0.12, y1 - 0.12):
                bl.sphere(f"rivet_{xx:.1f}_{yy:.1f}", (xx, yy, 0.09), 0.08, mat=br, scale=(1, 1, 0.5))
        dark = bl.simple_mat("dk", (0.05, 0.04, 0.03), rough=0.6)
        bs = 0.78 * LS(ctx)
        for i, (x, y) in enumerate(pz.left_ports):
            bl.box(f"badge_{i}", (-1.2, y, 0.05), (bs, bs * 0.9, 0.06), br, bevel=0.05)
            bl.box(f"badge_in_{i}", (-1.2, y, 0.081), (bs * 0.8, bs * 0.72, 0.01), dark, bevel=0.02)
            if pz.left_labels[i].isdigit():
                bl.text(f"ll_{i}", pz.left_labels[i], (-1.2, y, 0.086), bs * 0.4, mat=br, extrude=0.01)
            else:
                symbol_icon(f"sym_{i}", pz.left_labels[i], (-1.2, y), bs * 0.45, 0.085, 0.11, br)
            bl.cylinder(f"fit_{i}", (x - 0.25, y, r), 1.35 * r, 0.5, axis="X", mat=br)
            bl.cylinder(f"collar_{i}", (x - 0.05, y, r), 1.6 * r, 0.14, axis="X", mat=br, verts=8, bevel=0.01)
        bl.box("manifold", (W + 0.22, 0, r), (0.3, top - bot, 0.32), br, bevel=0.05)
        glass = bl.NT("gglass")
        glass.principled(**{"Base Color": (0.9, 0.9, 0.9), "Roughness": 0.03, "Transmission": 1.0})
        face = bl.simple_mat("gface", (0.85, 0.8, 0.68), rough=0.7)
        needle = bl.simple_mat("needle", (0.05, 0.05, 0.05), rough=0.4)
        gr = 0.34 * LS(ctx)
        for j, (x, y) in enumerate(pz.right_ports):
            bl.cylinder(f"rcol_{j}", (x - 0.05, y, r), 1.6 * r, 0.16, axis="X", mat=br, verts=8, bevel=0.01)
            gx = x + g_off
            bl.cylinder(f"gbez_{j}", (gx, y, 0.12), gr, 0.2, mat=br, bevel=0.02)
            bl.cylinder(f"gface_{j}", (gx, y, 0.225), gr * 0.85, 0.012, mat=face)
            a = rng.uniform(-2.2, 2.2)
            nd = bl.box(f"needle_{j}", (gx + 0.35 * gr * math.cos(a), y + 0.35 * gr * math.sin(a), 0.235), (0.7 * gr, 0.03, 0.01), needle)
            nd.rotation_euler[2] = a
            bw = max(0.42, 0.2 * len(pz.right_labels[j]) + 0.06) * LS(ctx)
            bcx = x + 0.47 + bw / 2
            bl.box(f"rbadge_{j}", (bcx, y, 0.05), (bw, 0.46 * LS(ctx), 0.06), br, bevel=0.03)
            bl.box(f"rbadge_in_{j}", (bcx, y, 0.081), (bw - 0.08 * LS(ctx), 0.38 * LS(ctx), 0.01), dark, bevel=0.01)
            bl.text(f"rl_{j}", pz.right_labels[j], (bcx, y, 0.086), 0.3 * LS(ctx), mat=br, extrude=0.01)
        return (x0 + 0.05, x1 - 0.05, y0 + 0.05, y1 - 0.05)

    def extras(self, pz, ctx):
        rng, r = ctx["rng"], ctx["r"]
        br = brass("collar", rough=(0.25, 0.45))
        for c, (i, j, x, y) in enumerate(free_spots(pz, ctx, int(rng.integers(*self.clips)), min_gap_r=6)):
            P = np.array(pz.cables[i])
            t = P[min(j + 2, len(P) - 1)] - P[max(j - 2, 0)]
            ang = math.atan2(t[1], t[0])
            ob = bl.cylinder(f"pcollar_{c}", (x, y, r), 1.3 * r, 0.22, axis="X", mat=br, verts=24, bevel=0.01)
            ob.rotation_euler = (0, math.pi / 2, ang)
            bl.box(f"pstrap_{c}", (x, y, 0.02), (0.18, 3.4 * r, 0.04), br, bevel=0.01).rotation_euler[2] = ang

    def lights(self, bounds, ctx):
        cx, cy, s, k = self.light_scale(bounds)
        x0, x1, y0, y1 = bounds
        bl.point_light("lantern", (x0 - 0.05 * s, y1 - 0.15 * s, 0.4 * s), 12000 * k, (1.0, 0.68, 0.35), radius=0.06 * s)
        bl.area_light("cold", (x1 + 0.3 * s, y1 + 0.2 * s, 0.9 * s), (cx, cy, 0), 700 * k, 0.7 * s, (0.5, 0.65, 1.0))
        bl.area_light("fill", (cx, y0 - 0.5 * s, 0.8 * s), (cx, cy, 0), 200 * k, 0.8 * s, (0.8, 0.8, 0.9))
        backdrop(bounds, (0.03, 0.04, 0.05))
        bl.world((0.02, 0.03, 0.04), 0.5)


# ----------------------------------------------------------------------------
# 5) retro synth (orange case, aluminium patch panel, patch cables with plugs)
# ----------------------------------------------------------------------------
class Synth(Theme):
    name = "synth"
    palette = [(0.08, 0.36, 0.45), (0.85, 0.35, 0.08), (0.92, 0.75, 0.15), (0.85, 0.80, 0.65)]
    camera_kw = dict(tilt_deg=(5, 12), lens=50)
    puzzle_overrides = dict(left_label_style="letters", right_label_style="numbers")
    use_waves = True

    def cable_material(self, color, ctx):
        return rubber_cable(color, "patch", contrast=0.05, rough=(0.35, 0.25), coat=0.35)

    def build(self, pz, ctx):
        W, H, r, n, pitch, rng = ctx["W"], ctx["H"], ctx["r"], ctx["n"], ctx["pitch"], ctx["rng"]
        top = H / 2 + 0.6 * pitch
        bot = -H / 2 - 0.6 * pitch
        x0, x1 = -2.3, W + 4.2
        y0, y1 = bot - 1.0, top + 1.0
        orange = bl.NT("enamel")
        tc = orange.texcoord()
        nz = orange.noise(tc.outputs["Object"], scale=2, detail=6)
        col = orange.ramp(nz.outputs["Fac"], [(0.35, (0.55, 0.16, 0.03)), (0.7, (0.75, 0.25, 0.06))])
        orange.principled(**{"Base Color": col.outputs[0], "Roughness": 0.35, "Coat": 0.5})
        bl.box("case", ((x0 + x1) / 2, (y0 + y1) / 2, -0.2), (x1 - x0, y1 - y0, 0.4), orange.mat, bevel=0.35, segments=6)
        alu = bl.NT("alu")
        tc = alu.texcoord()
        brush = alu.noise(alu.mapping(tc.outputs["Object"], scale=(0.5, 60, 1)), scale=8, detail=4)
        alu.principled(**{"Base Color": (0.62, 0.62, 0.6), "Metallic": 1.0,
                          "Roughness": alu.ramp(brush.outputs["Fac"], [(0.3, (0.25,) * 3), (0.7, (0.4,) * 3)]).outputs[0]})
        bl.box("alu", (W / 2 - 0.1, 0, 0.0), (W + 0.6, top - bot + 0.4, 0.06), alu.mat, bevel=0.02)
        teal = plastic("tealpanel", (0.05, 0.2, 0.24), rough=0.5, coat=0.2)
        bl.box("lpanel", (-1.15, 0, 0.0), (2.0, top - bot + 0.4, 0.07), teal, bevel=0.03)
        cream = plastic("cream", (0.85, 0.80, 0.66), rough=0.55, coat=0.1)
        ink = bl.simple_mat("ink", (0.08, 0.07, 0.06), rough=0.6)
        chrome = bl.simple_mat("chrome", (0.8, 0.8, 0.8), rough=0.12, metal=1.0)
        blk = bl.simple_mat("blk", (0.02, 0.02, 0.02), rough=0.4)
        plugm = plastic("plugbody", (0.85, 0.7, 0.1), rough=0.4, coat=0.4)
        ts = 0.62 * LS(ctx)
        waves = self.use_waves and n <= len(WAVES)
        if waves:
            pz.left_labels[:] = [str(w) for w in rng.permutation(WAVES)[:n]]
        for i, (x, y) in enumerate(pz.left_ports):
            bl.box(f"tag_{i}", (-1.45, y, 0.06), (ts * 1.4, ts * 1.05, 0.06), cream, bevel=0.06, segments=4)
            if waves:
                wave_icon(f"wave_{i}", pz.left_labels[i], (-1.45, y), ts * 0.62, 0.095, ink, rng, thick=0.022 * LS(ctx))
            else:
                bl.text(f"ll_{i}", pz.left_labels[i], (-1.45, y, 0.09), ts * 0.55, mat=ink, extrude=0.005)
            bl.cylinder(f"jack_{i}", (-0.62, y, 0.06), 0.2 * LS(ctx), 0.08, mat=chrome, verts=6, bevel=0.01)
            bl.cylinder(f"plug_{i}", (-0.25, y, r), 1.55 * r, 0.5, axis="X", mat=plugm, bevel=0.02)
            bl.cylinder(f"plugtip_{i}", (-0.55, y, r), 0.6 * r, 0.14, axis="X", mat=chrome)
        rpanel = plastic("rpanel", (0.05, 0.2, 0.24), rough=0.5, coat=0.2)
        bl.box("rpanel", (W + 2.3, 0, 0.0), (3.4, top - bot + 0.4, 0.07), rpanel, bevel=0.03)
        for j, (x, y) in enumerate(pz.right_ports):
            bl.cylinder(f"rjack_{j}", (x + 0.12, y, r), 1.5 * r, 0.28, axis="X", mat=chrome, verts=24, bevel=0.01)
            bl.cylinder(f"rplug_{j}", (x - 0.22, y, r), 1.5 * r, 0.42, axis="X", mat=plugm, bevel=0.02)
            bl.text(f"rl_{j}", pz.right_labels[j], (x + 0.62, y, 0.04), 0.4 * LS(ctx), mat=cream, extrude=0.005, align="LEFT")
        meter = bl.emissive("meter", (1.0, 0.7, 0.3), 1.2)
        needle = bl.simple_mat("needle", (0.05, 0.05, 0.05), rough=0.4)
        if top - bot > 3.0:
            for k, my in enumerate((top - 0.7, top - 1.9)):
                if my < bot + 1.6:
                    break
                bl.box(f"vu_{k}", (W + 2.6, my, 0.06), (1.9, 1.0, 0.06), blk, bevel=0.05)
                bl.box(f"vuf_{k}", (W + 2.6, my, 0.095), (1.7, 0.82, 0.01), meter)
                a = rng.uniform(0.6, 1.5)
                nd = bl.box(f"vun_{k}", (W + 2.6 + 0.3 * math.cos(a), my - 0.32 + 0.3 * math.sin(a), 0.11), (0.62, 0.035, 0.01), needle)
                nd.rotation_euler[2] = a
            kn = bl.simple_mat("knob", (0.03, 0.03, 0.03), rough=0.35)
            for k in range(3):
                bl.cylinder(f"knob_{k}", (W + 1.7 + k * 0.75, bot + 0.5, 0.12), 0.26, 0.2, mat=kn, verts=24, bevel=0.03)
        bl.box("handle", ((x0 + x1) / 2, y1 + 0.1, 0.0), (min(4, (x1 - x0) * 0.3), 0.25, 0.25), cream, bevel=0.1)
        return (x0 + 0.05, x1 - 0.05, y0 + 0.05, y1 + 0.2)

    def lights(self, bounds, ctx):
        cx, cy, s, k = self.light_scale(bounds)
        x0, x1, y0, y1 = bounds
        bl.area_light("sun", (x0 - 0.3 * s, y1 + 0.5 * s, 0.9 * s), (cx, cy, 0), 2400 * k, 0.6 * s, (1.0, 0.9, 0.75))
        bl.area_light("fill", (x1 + 0.4 * s, y0, 0.8 * s), (cx, cy, 0), 400 * k, 0.9 * s, (0.75, 0.85, 1.0))
        backdrop(bounds, (0.25, 0.18, 0.12), scale=0.3)
        bl.world((0.35, 0.33, 0.3), 0.4)


# ----------------------------------------------------------------------------
# 6) security system (steel frame, PCB, orange wires, shuffled number tags)
# ----------------------------------------------------------------------------
class Security(Theme):
    name = "security"
    palette = [(0.85, 0.35, 0.12), (0.15, 0.3, 0.7), (0.1, 0.1, 0.1)]
    camera_kw = dict(tilt_deg=(2, 8), lens=50)
    puzzle_overrides = dict(left_label_style="letters", right_label_style="numbers", shuffle_right_labels=True)

    def cable_material(self, color, ctx):
        return rubber_cable(color, "wire", contrast=0.06, rough=(0.4, 0.28), coat=0.25)

    def build(self, pz, ctx):
        W, H, r, n, pitch, rng = ctx["W"], ctx["H"], ctx["r"], ctx["n"], ctx["pitch"], ctx["rng"]
        top = H / 2 + 0.6 * pitch
        bot = -H / 2 - 0.6 * pitch
        x0, x1 = -1.6, W + 1.7
        y0, y1 = bot - 1.1, top + 1.3
        steel = worn_metal("frame", (0.45, 0.46, 0.48), rough=(0.3, 0.55), metal=0.9, scale=0.8)
        bl.box("frame", ((x0 + x1) / 2, (y0 + y1) / 2, -0.15), (x1 - x0, y1 - y0, 0.3), steel, bevel=0.1)
        pcb = bl.NT("pcb")
        tc = pcb.texcoord()
        nz = pcb.noise(tc.outputs["Object"], scale=3, detail=4)
        col = pcb.ramp(nz.outputs["Fac"], [(0.3, (0.03, 0.16, 0.07)), (0.7, (0.05, 0.22, 0.10))])
        pcb.principled(**{"Base Color": col.outputs[0], "Roughness": 0.45, "Coat": 0.1})
        bl.box("pcb", (W / 2, 0, 0.0), (W + 0.4, top - bot + 1.2, 0.04), pcb.mat)
        gold = bl.simple_mat("trace", (0.75, 0.6, 0.3), rough=0.35, metal=0.8)
        dirs = [np.array((math.cos(a), math.sin(a))) for a in np.arange(8) * math.pi / 4]
        for k in range(int(6 * W)):
            p = np.array((rng.uniform(0.2, W - 0.2), rng.uniform(bot - 0.4, top + 0.4)))
            d = int(rng.integers(0, 4)) * 2
            pts = [p.copy()]
            for _ in range(int(rng.integers(2, 6))):
                p = p + dirs[d] * rng.uniform(0.3, 1.8)
                p[0] = np.clip(p[0], 0.15, W - 0.15); p[1] = np.clip(p[1], bot - 0.5, top + 0.5)
                pts.append(p.copy())
                d = (d + int(rng.choice([-1, 1]))) % 8
            wdt = float(rng.choice([0.025, 0.04, 0.06]))
            bl.ribbon(f"trace_{k}", pts, wdt, 0.021, mat=gold)
            for q in (pts[0], pts[-1]):
                bl.cylinder(f"pad_{k}_{q[0]:.2f}", (q[0], q[1], 0.021), wdt * 1.8, 0.004, mat=gold, verts=16)
        chip = bl.simple_mat("chip", (0.03, 0.03, 0.03), rough=0.45)
        cap = bl.simple_mat("cap", (0.2, 0.25, 0.4), rough=0.3)
        for k in range(int(4 + W)):
            cx, cy = rng.uniform(1.0, W - 1.0), rng.uniform(bot, top)
            if rng.random() < 0.6:
                bl.box(f"chip_{k}", (cx, cy, 0.04), (rng.uniform(0.3, 0.8), rng.uniform(0.25, 0.6), 0.04), chip)
            else:
                bl.cylinder(f"cap_{k}", (cx, cy, 0.04), rng.uniform(0.08, 0.16), 0.05, mat=cap)
        red = plastic("btn_red", (0.55, 0.03, 0.03), rough=0.25, coat=0.6)
        chrome = bl.simple_mat("chrome", (0.75, 0.75, 0.78), rough=0.2, metal=1.0)
        white = bl.simple_mat("whitepaint", (0.85, 0.85, 0.82), rough=0.6)
        yel = plastic("tag_yellow", (0.85, 0.7, 0.05), rough=0.4)
        ink = bl.simple_mat("ink", (0.03, 0.03, 0.03), rough=0.6)
        bl.box("lstrip", (-0.9, 0, 0.05), (1.1, top - bot + 0.3, 0.1), bl.simple_mat("strip_dark", (0.04, 0.04, 0.045), 0.5), bevel=0.03)
        bl.box("rstrip", (W + 0.9, 0, 0.05), (1.1, top - bot + 0.3, 0.1), steel, bevel=0.03)
        for i, (x, y) in enumerate(pz.left_ports):
            bl.sphere(f"btn_{i}", (-1.15, y, 0.1), 0.14 * LS(ctx), mat=red, scale=(1, 1, 0.6))
            bl.text(f"ll_{i}", pz.left_labels[i], (-0.75, y, 0.1), 0.3 * LS(ctx), mat=white, extrude=0.002)
            bl.box(f"term_{i}", (x - 0.2, y, r), (0.4, 2.6 * r, 2.2 * r), chrome, bevel=0.02)
        for j, (x, y) in enumerate(pz.right_ports):
            bl.box(f"rterm_{j}", (x + 0.2, y, r), (0.4, 2.6 * r, 2.2 * r), chrome, bevel=0.02)
            tw_ = max(0.5, 0.22 * len(pz.right_labels[j]) + 0.08) * LS(ctx)
            tcx = x + 0.65 + tw_ / 2
            bl.box(f"rtag_{j}", (tcx, y, 0.12), (tw_, 0.5 * LS(ctx), 0.04), yel, bevel=0.03)
            bl.text(f"rl_{j}", pz.right_labels[j], (tcx, y, 0.142), 0.34 * LS(ctx), mat=ink, extrude=0.002)
        bl.text("title", "SECURITY SYSTEM", ((x0 + x1) / 2, y1 - 0.42, 0.0), 0.36,
                mat=bl.simple_mat("tt", (0.15, 0.15, 0.16), 0.5), extrude=0.01)
        return (x0 + 0.05, x1 - 0.05, y0 + 0.05, y1 - 0.05)

    def lights(self, bounds, ctx):
        cx, cy, s, k = self.light_scale(bounds)
        x0, x1, y0, y1 = bounds
        bl.area_light("key", (x0, y1 + 0.3 * s, 0.9 * s), (cx, cy, 0), 2200 * k, 0.5 * s, (1.0, 0.97, 0.92))
        bl.area_light("fill", (x1 + 0.3 * s, y0, 0.8 * s), (cx, cy, 0), 400 * k, 0.8 * s, (0.85, 0.9, 1.0))
        backdrop(bounds, (0.3, 0.32, 0.36), scale=0.3)
        bl.world((0.5, 0.52, 0.55), 0.4)


THEMES = {t.name: t for t in [Bomb(), Railway(), SciFi(), Steampunk(), Synth(), Security()]}
