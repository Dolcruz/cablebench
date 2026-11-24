"""Theme-independent cable puzzle logic.

Board coordinates: x to the right, y up, z out of the board.
Left ports sit at x = 0, right connectors at x = W. Index 0 is the top row.
All lengths are in board units; the cable radius r sets the scale.

Guarantees for every generated puzzle (checked, not hoped for):
  * every crossing has an angle >= min_cross_angle_deg
  * outside crossings, two cable centrelines never come closer than clearance*r
  * crossing points are at least min_cross_spacing*r apart
  * bend radius >= min_bend_radius*r
  * at every crossing the upper cable clears the lower one in z
"""
from __future__ import annotations

import collections
import json
import math
from dataclasses import dataclass, field, asdict

import numpy as np
from scipy.spatial import cKDTree


# ----------------------------------------------------------------------------
# configuration
# ----------------------------------------------------------------------------
@dataclass
class PuzzleConfig:
    n_cables: int = 8
    cable_radius: float = 0.11
    pitch: float = 0.9            # vertical distance between ports
    aspect: float = 1.35          # field width / field height
    waypoints: tuple = (2, 4)     # random waypoints per cable (min, max)
    swing: float = 0.45           # waypoint y deviation from the straight line (fraction of H)
    max_swing_pitches: float = 6.0  # ...but at most this many port pitches
    backtrack_prob: float = 0.12  # chance a waypoint goes backwards in x (loops)
    allow_self_cross: bool = True
    min_cross_angle_deg: float = 25.0
    clearance: float = 2.6        # min centre distance (in r) away from crossings
    min_bend_radius: float = 3.0  # in r
    min_cross_spacing: float = 3.5  # in r, between crossing points
    lead_frac: float = 0.06       # straight lead out of each port (fraction of W)
    over_under: str = "random"    # random | layered
    shuffle_right_labels: bool = False
    left_label_style: str = "letters"   # letters | numbers | words | symbols
    right_label_style: str = "numbers"
    iters_per_cable: int = 600
    seed: int = 0


WORDS = ["YARD A", "JUNCTION", "PLATFORM", "DEPOT", "SIGNAL N", "SIGNAL S",
         "SIDING", "YARD B", "BRIDGE", "TUNNEL", "CROSSING", "TURNTABLE",
         "GOODS", "SHED", "LOOP", "SPUR", "HARBOUR", "MILL", "QUARRY", "WEST",
         "EAST", "NORTH", "SOUTH", "SUMMIT", "VALLEY", "FERRY", "CHAPEL",
         "MARKET", "FOUNDRY", "DOCKS", "WATER", "COAL", "TIMBER", "SALT",
         "FIELD", "HILL", "LAKE", "FOREST", "CASTLE", "STATION"]
SYMBOLS = ["circle", "square", "triangle", "diamond", "hexagon", "star",
           "cross", "ring", "pentagon", "bar", "chevron", "dot"]


def _letters(n):
    out = []
    for i in range(n):
        s, k = "", i
        while True:
            s = chr(65 + k % 26) + s
            k = k // 26 - 1
            if k < 0:
                break
        out.append(s)
    return out


def make_labels(style, n, rng):
    if style == "letters":
        return _letters(n)
    if style == "numbers":
        return [str(i + 1) for i in range(n)]
    if style == "words":
        if n > len(WORDS):
            return [f"LINE {s}" for s in _letters(n)]
        return list(WORDS[:n])
    if style == "symbols":
        if n > len(SYMBOLS):
            raise ValueError("too many cables for symbol labels")
        return list(SYMBOLS[:n])
    raise ValueError(style)


# ----------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------
def bspline(points, samples_per_seg=30):
    """Clamped uniform cubic B-spline (approximating, smooth)."""
    P = np.asarray(points, float)
    P = np.vstack([P[0], P[0], P, P[-1], P[-1]])
    t = np.linspace(0, 1, samples_per_seg, endpoint=False)[:, None]
    b0 = (1 - t) ** 3 / 6
    b1 = (3 * t ** 3 - 6 * t ** 2 + 4) / 6
    b2 = (-3 * t ** 3 + 3 * t ** 2 + 3 * t + 1) / 6
    b3 = t ** 3 / 6
    out = [b0 * P[i] + b1 * P[i + 1] + b2 * P[i + 2] + b3 * P[i + 3] for i in range(len(P) - 3)]
    out.append(P[-1][None])
    return np.vstack(out)


def resample(poly, step):
    d = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(d)])
    n = max(int(math.ceil(s[-1] / step)), 2)
    si = np.linspace(0, s[-1], n + 1)
    return np.column_stack([np.interp(si, s, poly[:, k]) for k in range(poly.shape[1])])


def arclen(poly):
    d = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    return np.concatenate([[0], np.cumsum(d)])


def curvature(poly):
    v = np.diff(poly, axis=0)
    ln = np.linalg.norm(v, axis=1)
    u = v / ln[:, None]
    ang = np.arccos(np.clip((u[1:] * u[:-1]).sum(1), -1, 1))
    ds = 0.5 * (ln[1:] + ln[:-1])
    return ang / ds


def _seg_x(p, r, q, s):
    """Vectorised segment intersection p+t r, q+u s. Returns t,u,ok."""
    rxs = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
    qp = q - p
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / rxs
        u = (qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]) / rxs
    ok = (np.abs(rxs) > 1e-12) & (t >= 0) & (t < 1) & (u >= 0) & (u < 1)
    return t, u, ok


def _angle(r, s):
    ra = r / np.linalg.norm(r, axis=-1, keepdims=True)
    sb = s / np.linalg.norm(s, axis=-1, keepdims=True)
    return np.arccos(np.clip(np.abs((ra * sb).sum(-1)), 0, 1))


def find_crossings(polys, step):
    """All crossings among a list of polylines (including self crossings).

    Returns list of (a, ta, b, tb, point, angle) with fractional indices.
    """
    pts, own, idx = [], [], []
    for c, P in enumerate(polys):
        m = 0.5 * (P[:-1] + P[1:])
        pts.append(m); own.append(np.full(len(m), c)); idx.append(np.arange(len(m)))
    pts = np.vstack(pts); own = np.concatenate(own); idx = np.concatenate(idx)
    seglen = max(float(np.max(np.linalg.norm(np.diff(P, axis=0), axis=1))) for P in polys)
    tree = cKDTree(pts)
    pairs = tree.query_pairs(seglen * 1.05, output_type="ndarray")
    if len(pairs) == 0:
        return []
    i, j = pairs[:, 0], pairs[:, 1]
    same = own[i] == own[j]
    keep = ~same | (np.abs(idx[i] - idx[j]) > 2)
    i, j = i[keep], j[keep]
    if len(i) == 0:
        return []
    A0 = np.array([polys[own[k]][idx[k]] for k in i]); A1 = np.array([polys[own[k]][idx[k] + 1] for k in i])
    B0 = np.array([polys[own[k]][idx[k]] for k in j]); B1 = np.array([polys[own[k]][idx[k] + 1] for k in j])
    t, u, ok = _seg_x(A0, A1 - A0, B0, B1 - B0)
    out = []
    for k in np.nonzero(ok)[0]:
        a, b = int(own[i[k]]), int(own[j[k]])
        ta, tb = idx[i[k]] + t[k], idx[j[k]] + u[k]
        pt = A0[k] + t[k] * (A1[k] - A0[k])
        ang = float(_angle(A1[k] - A0[k], B1[k] - B0[k]))
        if a > b or (a == b and ta > tb):
            a, b, ta, tb = b, a, tb, ta
        out.append((a, float(ta), b, float(tb), pt, ang))
    return out


# ----------------------------------------------------------------------------
# generation
# ----------------------------------------------------------------------------
@dataclass
class Puzzle:
    config: dict
    W: float
    H: float
    left_ports: list
    right_ports: list
    left_labels: list
    right_labels: list
    perm: list                    # left i -> right slot perm[i]
    cables: list                  # list of (n,3) point lists, start at left port
    waypoints: list
    crossings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def solution(self):
        return {self.left_labels[i]: self.right_labels[self.perm[i]]
                for i in range(len(self.perm))}

    def to_json(self):
        d = asdict(self)
        d["solution"] = self.solution()
        return d


class Router:
    def __init__(self, cfg, rng, W, H, ys, perm):
        self.cfg, self.rng, self.W, self.H, self.ys, self.perm = cfg, rng, W, H, ys, perm
        r = cfg.cable_radius
        self.r = r
        self.lead = cfg.lead_frac * W
        self.ymin = -H / 2 - 0.6 * cfg.pitch
        self.ymax = H / 2 + 0.6 * cfg.pitch
        self.clear = cfg.clearance * r
        self.min_ang = math.radians(cfg.min_cross_angle_deg)
        self.kmax = 1.0 / (cfg.min_bend_radius * r)
        self.step = 0.6 * r
        self.placed = {}          # i -> (waypoints, coarse polyline)
        self.cross = {}           # i -> crossings recorded when i was placed
        self._rebuild()

    # -- path construction ----------------------------------------------------
    def new_waypoints(self, i):
        cfg, rng, W = self.cfg, self.rng, self.W
        k = rng.integers(cfg.waypoints[0], cfg.waypoints[1] + 1)
        xs = np.sort(rng.uniform(0.16 * W, 0.84 * W, k))
        for j in range(k):
            if rng.random() < cfg.backtrack_prob:
                xs[j] += rng.uniform(-0.25, 0.1) * W
        xs = np.clip(xs, 0.14 * W, 0.86 * W)
        y0, y1 = self.ys[i], self.ys[self.perm[i]]
        swing = min(max(cfg.swing * self.H, 2.5 * cfg.pitch), cfg.max_swing_pitches * cfg.pitch)
        base = y0 + (y1 - y0) * (xs / W)
        wy = np.clip(base + rng.uniform(-swing, swing, k), self.ymin, self.ymax)
        return np.column_stack([xs, wy])

    def path(self, i, wp, step):
        W, lead = self.W, self.lead
        y0, y1 = self.ys[i], self.ys[self.perm[i]]
        pts = [(0, y0), (lead * 0.7, y0), (lead * 1.4, y0), (lead * 2.4, y0)]
        pts += [tuple(p) for p in wp]
        pts += [(W - 2.4 * lead, y1), (W - 1.4 * lead, y1), (W - lead * 0.7, y1), (W, y1)]
        return resample(bspline(pts, 40), step)

    # -- index of placed cables -----------------------------------------------
    def _rebuild(self):
        pts, own, idx = [], [], []
        for c, (_, P) in self.placed.items():
            pts.append(P); own.append(np.full(len(P), c)); idx.append(np.arange(len(P)))
        if pts:
            self.pts = np.vstack(pts); self.own = np.concatenate(own); self.idx = np.concatenate(idx)
            self.tree = cKDTree(self.pts)
        else:
            self.tree = None
        cp = [c[4] for lst in self.cross.values() for c in lst]
        self.ctree = cKDTree(np.array(cp)) if cp else None

    # -- scoring --------------------------------------------------------------
    def evaluate(self, i, P):
        """Return (penalty, violation_points, blamed_cables, crossings)."""
        cfg, r = self.cfg, self.r
        pen = 0.0
        locs = []
        blame = collections.Counter()
        # bounds
        out = np.maximum(self.ymin - 0.2 - P[:, 1], P[:, 1] - self.ymax - 0.2)
        if out.max() > 0:
            pen += 5 + 10 * out.max(); locs.append(P[np.argmax(out)])
        s = arclen(P)
        inner = (P[:, 0] > self.lead * 0.5) & (P[:, 0] < self.W - self.lead * 0.5)
        bad = ~inner & (s > 3 * self.lead) & (s < s[-1] - 3 * self.lead)
        if bad.any():
            pen += 5 + bad.sum() * 0.2; locs.append(P[np.argmax(bad)])
        # curvature
        k = curvature(P)
        exc = k > self.kmax
        if exc.any():
            pen += 3 + exc.sum() * 0.3; locs.append(P[int(np.argmax(k)) + 1])
        crosses = []
        # self crossings / proximity
        for (_, ta, _, tb, pt, ang) in find_crossings([P], self.step):
            if not cfg.allow_self_cross:
                pen += 3; locs.append(pt)
            if ang < self.min_ang:
                pen += 2 + 4 * (self.min_ang - ang); locs.append(pt)
            crosses.append((i, ta, i, tb, pt, ang))
        st = cKDTree(P)
        prs = st.query_pairs(self.clear, output_type="ndarray")
        if len(prs):
            far = np.abs(prs[:, 0] - prs[:, 1]) * self.step > 8 * r
            for a, b in prs[far]:
                p = P[a]
                if not any(np.linalg.norm(p - c[4]) < self.clear / math.sin(max(c[5], 0.1)) + 1.5 * r
                           for c in crosses):
                    pen += 0.3; locs.append(p)
        # other cables
        if self.tree is not None:
            near = self.tree.query_ball_point(P, self.clear)
            lens = np.fromiter((len(l) for l in near), int, len(near))
            if lens.sum():
                A = np.repeat(np.arange(len(P)), lens)
                M = np.fromiter((m for l in near for m in l), int, int(lens.sum()))
                nown = len(self.own)
                cand = []
                for da in (-1, 0):
                    for dm in (-1, 0):
                        aa, mm = A + da, M + dm
                        ok = (aa >= 0) & (aa < len(P) - 1) & (mm >= 0) & (mm + 1 < nown)
                        aa, mm, m0 = aa[ok], mm[ok], M[ok]
                        ok2 = (self.own[mm] == self.own[m0]) & (self.own[mm + 1] == self.own[m0])
                        cand.append(np.column_stack([aa[ok2], mm[ok2]]))
                sp = np.unique(np.vstack(cand), axis=0)
                if len(sp):
                    A0, A1 = P[sp[:, 0]], P[sp[:, 0] + 1]
                    B0, B1 = self.pts[sp[:, 1]], self.pts[sp[:, 1] + 1]
                    t, u, okx = _seg_x(A0, A1 - A0, B0, B1 - B0)
                    for kk in np.nonzero(okx)[0]:
                        o = int(self.own[sp[kk, 1]])
                        pt = A0[kk] + t[kk] * (A1[kk] - A0[kk])
                        ang = float(_angle(A1[kk] - A0[kk], B1[kk] - B0[kk]))
                        tb = self.idx[sp[kk, 1]] + u[kk]
                        if ang < self.min_ang:
                            pen += 2 + 4 * (self.min_ang - ang); locs.append(pt); blame[o] += 1
                        crosses.append((i, sp[kk, 0] + t[kk], o, tb, pt, ang))
                # proximity that is not explained by a nearby crossing with the same cable
                CO = self.own[M]
                CP = P[A]
                oc = [c for c in crosses if c[2] != i]
                if oc:
                    cpt = np.array([c[4] for c in oc]); cown = np.array([c[2] for c in oc])
                    crad = np.array([self.clear / math.sin(max(c[5], 0.1)) + 1.5 * r for c in oc])
                    d = np.linalg.norm(CP[:, None, :] - cpt[None, :, :], axis=2)
                    explained = ((d < crad[None, :]) & (CO[:, None] == cown[None, :])).any(axis=1)
                else:
                    explained = np.zeros(len(CP), bool)
                bad = np.flatnonzero(~explained)
                if len(bad):
                    pen += 0.3 * len(bad)
                    for b in bad[:: max(1, len(bad) // 8)]:
                        locs.append(CP[b])
                    for o, cnt in zip(*np.unique(CO[bad], return_counts=True)):
                        blame[int(o)] += int(cnt)
        # spacing between crossing points
        if crosses:
            cp = np.array([c[4] for c in crosses])
            lim = cfg.min_cross_spacing * r
            if len(cp) > 1:
                d = np.linalg.norm(cp[:, None] - cp[None], axis=2)
                np.fill_diagonal(d, 1e9)
                for a, b in np.argwhere(np.triu(d < lim)):
                    pen += 1; locs.append(cp[a])
            if self.ctree is not None:
                for a, lst in enumerate(self.ctree.query_ball_point(cp, lim)):
                    if lst:
                        pen += len(lst); locs.append(cp[a])
                        if crosses[a][2] != i:
                            blame[crosses[a][2]] += 1
        return pen, locs, blame, crosses

    # -- placement ------------------------------------------------------------
    def mutate(self, wp, locs):
        rng, W, H = self.rng, self.W, self.H
        wp = wp.copy()
        u = rng.random()
        if u < 0.08 and len(wp) < self.cfg.waypoints[1] + 1:
            x = rng.uniform(0.16 * W, 0.84 * W)
            wp = np.vstack([wp, [x, rng.uniform(self.ymin, self.ymax)]])
            return wp[np.argsort(wp[:, 0])]
        if u < 0.14 and len(wp) > 1:
            return np.delete(wp, rng.integers(len(wp)), axis=0)
        if locs and rng.random() < 0.75:
            p = locs[rng.integers(len(locs))]
            k = int(np.argmin(np.abs(wp[:, 0] - p[0])))
        else:
            k = rng.integers(len(wp))
        sc = rng.choice([0.03, 0.08, 0.2])
        wp[k, 1] = np.clip(wp[k, 1] + rng.normal(0, sc * H + 0.3), self.ymin, self.ymax)
        wp[k, 0] = np.clip(wp[k, 0] + rng.normal(0, sc * 0.5 * W), 0.14 * W, 0.86 * W)
        return wp

    def route(self, i):
        best_blame = collections.Counter()
        iters = self.cfg.iters_per_cable
        it = 0
        while it < iters:
            wp = self.new_waypoints(i)
            P = self.path(i, wp, self.step)
            pen, locs, blame, cr = self.evaluate(i, P)
            stall = 0
            while it < iters and pen > 0 and stall < 120:
                it += 1
                wp2 = self.mutate(wp, locs)
                P2 = self.path(i, wp2, self.step)
                pen2, locs2, blame2, cr2 = self.evaluate(i, P2)
                if pen2 <= pen:
                    stall = 0 if pen2 < pen else stall + 1
                    wp, P, pen, locs, blame, cr = wp2, P2, pen2, locs2, blame2, cr2
                else:
                    stall += 1
            if pen == 0:
                return wp, P, cr, it
            best_blame.update(blame)
        return None, None, best_blame, it

    def run(self):
        n = self.cfg.n_cables
        queue = list(self.rng.permutation(n))
        total, backtracks = 0, 0
        while queue:
            i = queue.pop(0)
            wp, P, cr, it = self.route(i)
            total += it
            if wp is None:
                backtracks += 1
                if backtracks > 6 * n or not self.placed:
                    raise RuntimeError(f"could not route cable {i} (n={n}); relax parameters")
                cands = [c for c, _ in cr.most_common() if c in self.placed]
                victims = cands[:2] if cands else [self.rng.choice(list(self.placed))]
                for v in victims:
                    del self.placed[v]
                    self.cross.pop(v, None)
                    queue.append(v)
                for k in list(self.cross):
                    self.cross[k] = [c for c in self.cross[k] if c[2] in self.placed or c[2] == k]
                queue.insert(0, i)
                self._rebuild()
                continue
            self.placed[i] = (wp, P)
            self.cross[i] = cr
            self._rebuild()
        return total, backtracks


def generate(cfg: PuzzleConfig) -> Puzzle:
    rng = np.random.default_rng(cfg.seed)
    n, r = cfg.n_cables, cfg.cable_radius
    H = (n - 1) * cfg.pitch
    W = max(H, 3 * cfg.pitch) * cfg.aspect + 2.0
    ys = np.array([H / 2 - i * cfg.pitch for i in range(n)])
    perm = rng.permutation(n)
    router = Router(cfg, rng, W, H, ys, perm)
    attempts, backtracks = router.run()

    fine_step = 0.3 * r
    P2 = [router.path(i, router.placed[i][0], fine_step) for i in range(n)]
    wps = [router.placed[i][0].tolist() for i in range(n)]
    crossings = find_crossings(P2, fine_step)

    min_ang = min((c[5] for c in crossings), default=math.pi / 2)
    if math.degrees(min_ang) < cfg.min_cross_angle_deg - 3:
        raise RuntimeError("crossing angle check failed on fine geometry")

    # over/under assignment
    layer = rng.permutation(n)
    xinfo = []
    for (a, ta, b, tb, pt, ang) in crossings:
        if cfg.over_under == "layered" and a != b:
            top_a = layer[a] > layer[b]
        else:
            top_a = bool(rng.random() < 0.5)
        if top_a:
            xinfo.append(dict(top=a, t_top=ta, bot=b, t_bot=tb, point=pt.tolist(), angle=ang))
        else:
            xinfo.append(dict(top=b, t_top=tb, bot=a, t_bot=ta, point=pt.tolist(), angle=ang))

    # heights: lift the upper cable smoothly over the lower one
    S = [arclen(p) for p in P2]
    idxs = [np.arange(len(s)) for s in S]
    gap = 0.12 * r

    def solve_heights():
        bumps = {}  # crossing id -> (cable, s_center, height, flat, ramp)

        def heights(k):
            z = np.full(len(S[k]), r)
            for (c, sc, h, f, L) in bumps.values():
                if c != k:
                    continue
                d = np.abs(S[k] - sc)
                prof = np.where(d < f, 1.0, np.where(d < f + L, 0.5 * (1 + np.cos(math.pi * (d - f) / L)), 0.0))
                z = np.maximum(z, r + h * prof)
            return z

        for _ in range(25):
            Z = [heights(k) for k in range(n)]
            bad = []
            for xid, x in enumerate(xinfo):
                a, b = x["top"], x["bot"]
                zb = np.interp(x["t_bot"], idxs[b], Z[b])
                za = np.interp(x["t_top"], idxs[a], Z[a])
                need = zb + 2 * r + gap
                if za < need - 1e-6:
                    bad.append((xid, need))
            if not bad:
                return Z, []
            for xid, need in bad:
                x = xinfo[xid]
                a = x["top"]
                sa = float(np.interp(x["t_top"], idxs[a], S[a]))
                h = need - r
                f = r / max(math.sin(math.radians(x["angle"]) if x["angle"] > 3.2 else x["angle"]), 0.3) + 0.4 * r
                L = max(3.5 * r, 2.2 * h)
                bumps[xid] = (a, sa, h, f, L)
            if max(z.max() for z in Z) > 9 * r:
                break
        return None, [xid for xid, _ in bad]

    for _round in range(40):
        Z, bad = solve_heights()
        if Z is not None:
            break
        for xid in bad:  # flip offending crossings and retry
            x = xinfo[xid]
            if rng.random() < 0.5:
                x["top"], x["bot"], x["t_top"], x["t_bot"] = x["bot"], x["top"], x["t_bot"], x["t_top"]
    else:
        raise RuntimeError("over/under clearance could not be resolved")
    cables3 = [np.column_stack([P2[k], Z[k]]).tolist() for k in range(n)]

    left_labels = make_labels(cfg.left_label_style, n, rng)
    right_labels = make_labels(cfg.right_label_style, n, rng)
    if cfg.shuffle_right_labels:
        right_labels = [right_labels[j] for j in rng.permutation(n)]

    per_cable = [0] * n
    for x in xinfo:
        per_cable[x["top"]] += 1
        if x["bot"] != x["top"]:
            per_cable[x["bot"]] += 1
    stats = dict(
        n_crossings=len(xinfo),
        n_self_crossings=sum(1 for x in xinfo if x["top"] == x["bot"]),
        crossings_per_cable=per_cable,
        min_cross_angle_deg=round(math.degrees(min_ang), 1),
        mean_length=round(float(np.mean([s[-1] for s in S])), 3),
        max_lift=round(float(max(z.max() for z in Z) / r), 2),
        router_iterations=attempts,
        backtracks=backtracks,
    )
    for x in xinfo:
        x["angle"] = round(math.degrees(x["angle"]), 1)

    return Puzzle(config=asdict(cfg), W=W, H=H,
                  left_ports=[[0.0, float(y)] for y in ys],
                  right_ports=[[float(W), float(y)] for y in ys],
                  left_labels=left_labels, right_labels=right_labels,
                  perm=[int(p) for p in perm], cables=cables3, waypoints=wps,
                  crossings=xinfo, stats=stats)


if __name__ == "__main__":
    import sys, time
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    t = time.time()
    pz = generate(PuzzleConfig(n_cables=n, seed=seed))
    st = dict(pz.stats); st.pop("crossings_per_cable")
    print(n, json.dumps(st), f"{time.time() - t:.1f}s")
