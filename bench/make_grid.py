#!/usr/bin/env python3
"""Generate a cablebench grid: cable count n x difficulty level, k items per cell.

Two phases, so routing (pure Python, CPU, one process per puzzle) and rendering
(Blender, GPU) can run on different machines:

  python bench/make_grid.py route  --grid pilot --n 5,10,20,30,50,70,100 --levels calm,bundles,hard --per-cell 2
  python bench/make_grid.py render --grid pilot            (needs bpy: .venv\\Scripts\\python.exe)
  python bench/make_grid.py status --grid pilot

Output goes OUTSIDE the repo (default %USERPROFILE%/cablebench-data/<grid>), because the
manifest holds the solutions. Puzzle seeds are random per attempt and mixed with a secret
salt from %USERPROFILE%/.cablebench_salt (created on first use, never committed), so the
public generator cannot rebuild an item even if a seed leaks.

Routing has no time limit: an attempt runs until it succeeds or the router reports a dead end
(e.g. bundles blocking each other); a dead end is retried with a new seed until the item is
routed. Idle workers start extra attempts with other seeds for items still open, the first one
to finish wins and its siblings are stopped. Every attempt is logged in jobs.jsonl.
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import pickle
import secrets
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA = os.path.join(os.path.expanduser("~"), "cablebench-data")
SALT_FILE = os.path.join(os.path.expanduser("~"), ".cablebench_salt")

# difficulty levels: preset, port pitch, bundles(n), loose distractor pieces(n)
BUNDLES = {5: 1, 10: 1, 20: 2, 30: 3, 50: 4, 70: 4, 100: 5}
HARD_BUNDLES = {5: 0, 10: 1, 20: 2, 30: 2, 50: 2, 70: 2, 100: 3}
LEVELS = {
    "calm": dict(preset="normal", pitch=1.3, bundles=lambda n: 0, loose=lambda n: 0),
    "bundles": dict(preset="normal", pitch=1.3, bundles=lambda n: BUNDLES.get(n, 4), loose=lambda n: max(1, n // 10)),
    "hard": dict(preset="hard", pitch=1.1, bundles=lambda n: HARD_BUNDLES.get(n, 2), loose=lambda n: max(1, n // 10)),
}
THEME_CYCLE = ["railway", "scifi", "steampunk", "synth", "security"]   # no bomb: triggers safety refusals
# copy of Theme.puzzle_overrides (themes.py imports bpy); the render phase checks they still match
THEME_OVR = {
    "railway": dict(left_label_style="words", right_label_style="numbers"),
    "scifi": dict(left_label_style="symbols", right_label_style="numbers"),
    "steampunk": dict(left_label_style="symbols", right_label_style="numbers", cable_radius=0.13, pitch=1.0,
                      min_bend_radius=3.5),
    "synth": dict(left_label_style="letters", right_label_style="numbers"),
    "security": dict(left_label_style="letters", right_label_style="numbers", shuffle_right_labels=True),
}


def label_scale(n, big=1.4):
    """Labels grow with the board: 4K caps the image, so above ~50 ports the text would shrink below
    ~13 px (railway numbers on dark plates were barely readable at 50). 1.4 was checked in all five themes
    with 3-digit labels (bench/label_test.py)."""
    return 1.0 if n < 50 else (1.2 if n < 70 else big)


def auto_res(n, cap_h=2160):
    h = min(max(900, int(70 * n)), cap_h)
    return (int(round(h * 16 / 9 / 16) * 16), int(round(h / 16) * 16))


def get_salt():
    if not os.path.exists(SALT_FILE):
        with open(SALT_FILE, "w") as f:
            f.write(str(secrets.randbits(62)))
        print(f"new secret salt written to {SALT_FILE} (keep it out of every repo)")
    return int(open(SALT_FILE).read().strip())


def grid_dir(a):
    return os.path.join(a.data, a.grid)


# ----------------------------------------------------------------------------- jobs
def make_jobs(a):
    jobs = []
    k = 0
    for lev in a.levels.split(","):
        for n in [int(x) for x in a.n.split(",")]:
            for c in range(a.per_cell):
                theme = THEME_CYCLE[(k + c) % len(THEME_CYCLE)]
                jobs.append(dict(id=f"g_{lev}_n{n:03d}_{c:02d}", n=n, level=lev, theme=theme, rep=c))
            k += 1
    return jobs


def build_cfg(job, seed, salt):
    from cablebench.puzzle import PuzzleConfig, PRESETS
    lv = LEVELS[job["level"]]
    n = job["n"]
    cfg = PuzzleConfig(n_cables=n, seed=seed, seed_salt=salt, pitch=lv["pitch"])
    for k, v in PRESETS[lv["preset"]].items():
        setattr(cfg, k, v)
    cfg.bundles = lv["bundles"](n)
    cfg.require_bundles = cfg.bundles > 0
    cfg.loose = lv["loose"](n)
    for k, v in THEME_OVR[job["theme"]].items():
        setattr(cfg, k, v)
    if cfg.left_label_style == "symbols" and n > 12:
        cfg.left_label_style = "numbers"   # the symbol themes switch to numbers above 12 ports anyway
    return cfg


def _attempt(job, seed, salt, out_pkl, err_file):
    try:
        from cablebench.puzzle import generate
        cfg = build_cfg(job, seed, salt)
        t0 = time.time()
        pz = generate(cfg)
        tmp = f"{out_pkl}.{seed}.tmp"
        with open(tmp, "wb") as f:
            pickle.dump(dict(job=job, seed=seed, puzzle=pz, route_s=round(time.time() - t0, 1)), f)
        os.replace(tmp, out_pkl)
    except Exception as e:
        with open(err_file, "w") as f:
            f.write(f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")


def cmd_route(a):
    gd = grid_dir(a)
    pdir = os.path.join(gd, "puzzles")
    os.makedirs(pdir, exist_ok=True)
    salt = get_salt()
    jobs = make_jobs(a)
    json.dump(dict(grid=a.grid, n=a.n, levels=a.levels, per_cell=a.per_cell, max_attempts=a.max_attempts,
                   level_defs={k: dict(preset=v["preset"], pitch=v["pitch"],
                   bundles={n: v["bundles"](n) for n in BUNDLES}, loose={n: v["loose"](n) for n in BUNDLES})
                   for k, v in LEVELS.items()}, themes=THEME_CYCLE),
              open(os.path.join(gd, "grid.json"), "w"), indent=1)
    log = open(os.path.join(gd, "jobs.jsonl"), "a")
    todo = [j for j in jobs if not os.path.exists(os.path.join(pdir, j["id"] + ".pkl"))]
    print(f"{len(jobs)} jobs, {len(todo)} to route, {a.workers} workers, no time limit", flush=True)
    prev = collections.Counter()
    if os.path.exists(os.path.join(gd, "jobs.jsonl")):
        for l in open(os.path.join(gd, "jobs.jsonl")):
            if l.strip():
                prev[json.loads(l)["id"]] += 1
    tries = {j["id"]: prev[j["id"]] for j in todo}
    open_jobs = sorted(todo, key=lambda j: -j["n"])   # big ones first
    gave_up = set()
    live = {}   # attempt key -> (process, job, seed, start, out, err)
    t_start = time.time()

    def write(jid, att, status, dt, msg):
        rec = dict(id=jid, attempt=att, status=status, seconds=round(dt, 1), msg=msg[:200],
                   time=time.strftime("%Y-%m-%d %H:%M:%S"))   # seeds stay in the pickle only
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(f"[{(time.time() - t_start) / 60:6.1f} min] {jid:22s} try {att} {status:8s} {dt:6.0f}s {msg[:80]}",
              flush=True)

    while open_jobs or live:
        # fill free workers: the open job with the fewest running attempts goes next (big ones first)
        while open_jobs and len(live) < a.workers:
            running = collections.Counter(v[1]["id"] for v in live.values())
            j = min(open_jobs, key=lambda j: running[j["id"]])
            tries[j["id"]] += 1
            att = tries[j["id"]]
            seed = secrets.randbits(31)
            out = os.path.join(pdir, j["id"] + ".pkl")
            err = os.path.join(pdir, f"{j['id']}.err{att}")
            p = mp.Process(target=_attempt, args=(j, seed, salt, out, err), daemon=True)
            p.start()
            live[(j["id"], att)] = (p, j, seed, time.time(), out, err)
        time.sleep(2)
        for key, (p, j, seed, t0, out, err) in list(live.items()):
            if p.is_alive():
                continue
            jid, att = key
            del live[key]
            dt = time.time() - t0
            status = "ok" if os.path.exists(out) else ("error" if os.path.exists(err) else "died")
            msg = open(err).read().splitlines()[0] if os.path.exists(err) else ""
            write(jid, att, status, dt, msg)
            if status == "ok":
                open_jobs = [o for o in open_jobs if o["id"] != jid]
                for k2, v2 in list(live.items()):   # stop the sibling attempts of this item
                    if k2[0] == jid:
                        v2[0].kill()
                        v2[0].join()
                        del live[k2]
                        write(jid, k2[1], "stopped", time.time() - v2[3], "another attempt finished first")
            elif a.max_attempts and tries[jid] >= a.max_attempts and jid not in gave_up:
                gave_up.add(jid)
                open_jobs = [o for o in open_jobs if o["id"] != jid]
                print(f"GAVE UP {jid} after {tries[jid]} attempts (--max-attempts)", flush=True)
    done = sum(os.path.exists(os.path.join(pdir, j["id"] + ".pkl")) for j in jobs)
    print(f"routed {done}/{len(jobs)} in {(time.time() - t_start) / 60:.1f} min")


# ----------------------------------------------------------------------------- render
def cmd_render(a):
    import uuid
    import numpy as np
    os.environ.setdefault("CABLEBENCH_DEVICE", a.device)
    from cablebench import bl
    from cablebench.render import build, ground_truth, overlay
    from cablebench.themes import THEMES
    from generate import make_prompt
    gd = grid_dir(a)
    pdir, mdir, gtdir = (os.path.join(gd, x) for x in ("puzzles", "meta", "gt"))
    os.makedirs(mdir, exist_ok=True)
    os.makedirs(gtdir, exist_ok=True)
    for t, ovr in THEME_OVR.items():
        assert THEMES[t].puzzle_overrides == ovr, f"THEME_OVR out of sync for {t}"
    man_path = os.path.join(gd, "manifest.jsonl")
    have = set()
    if os.path.exists(man_path):
        have = {json.loads(l)["id"] for l in open(man_path) if l.strip()}
    pk = sorted(f for f in os.listdir(pdir) if f.endswith(".pkl"))
    if a.ids:
        pk = [f for f in pk if f[:-4] in a.ids.split(",")]
    man = open(man_path, "a")
    for f in pk:
        jid = f[:-4]
        if jid in have:
            continue
        d = pickle.load(open(os.path.join(pdir, f), "rb"))
        job, pz, seed = d["job"], d["puzzle"], d["seed"]
        n = job["n"]
        res = auto_res(n)
        ls = label_scale(n, a.big_label_scale)
        rng = np.random.default_rng([seed, get_salt(), 7919])
        t0 = time.time()
        theme = THEMES[job["theme"]]
        build(pz, theme, rng, color_mode="uniform", res=res, samples=a.samples, extras=True, label_scale=ls)
        name = "cb_" + uuid.uuid4().hex[:10]
        img = os.path.join(gd, name + ".png")
        bl.render(img)
        paths, lp, rp = ground_truth(pz, theme)
        meta = dict(id=jid, image=name + ".png", theme=theme.name, resolution=list(res), label_scale=ls,
                    left_labels=pz.left_labels, right_labels=pz.right_labels, solution=pz.solution(),
                    stats=pz.stats, left_ports_px=lp, right_ports_px=rp, cable_paths_px=paths,
                    puzzle=pz.to_json(), job=job, route_s=d["route_s"], render_s=round(time.time() - t0, 1))
        json.dump(meta, open(os.path.join(mdir, jid + ".json"), "w"))
        gtj = os.path.join(gtdir, jid + "_gt.png")
        overlay(img, meta, gtj)
        try:
            from PIL import Image
            Image.open(gtj).convert("RGB").save(gtj[:-4] + ".jpg", quality=80)
            os.remove(gtj)
        except Exception:
            pass
        st = pz.stats
        rec = dict(id=jid, image=meta["image"], theme=theme.name, n_cables=n, level=job["level"],
                   color_mode="uniform", prompt=make_prompt(meta), answer=meta["solution"],
                   n_crossings=st["n_crossings"], n_loose=st["n_loose"], bundles=len(st["bundles"] or []),
                   min_cross_angle_deg=st["min_cross_angle_deg"], resolution=list(res), label_scale=ls,
                   occluded=bool((meta.get("notes") or {}).get("occluder")))
        man.write(json.dumps(rec) + "\n")
        man.flush()
        print(f"{jid:22s} {theme.name:9s} {res[0]}x{res[1]} crossings={st['n_crossings']:5d} "
              f"min_angle={st['min_cross_angle_deg']:5.1f} render={meta['render_s']:.0f}s", flush=True)


def cmd_status(a):
    gd = grid_dir(a)
    pdir = os.path.join(gd, "puzzles")
    logs = [json.loads(l) for l in open(os.path.join(gd, "jobs.jsonl"))] if os.path.exists(os.path.join(gd, "jobs.jsonl")) else []
    man = [json.loads(l) for l in open(os.path.join(gd, "manifest.jsonl"))] if os.path.exists(os.path.join(gd, "manifest.jsonl")) else []
    by = {}
    for r in logs:
        by.setdefault(r["id"], []).append(r)
    print(f"{'id':22s} attempts  last     route_s")
    for jid, rs in sorted(by.items()):
        ok = [r for r in rs if r["status"] == "ok"]
        print(f"{jid:22s} {len(rs):3d}      {rs[-1]['status']:8s} {ok[0]['seconds'] if ok else '-'}")
    print(f"routed {len([f for f in os.listdir(pdir) if f.endswith('.pkl')]) if os.path.isdir(pdir) else 0}, rendered {len(man)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["route", "render", "status"])
    ap.add_argument("--grid", default="pilot")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--n", default="5,10,20,30,50,70,100")
    ap.add_argument("--levels", default="calm,bundles,hard")
    ap.add_argument("--per-cell", type=int, default=2)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 4))
    ap.add_argument("--max-attempts", type=int, default=0, help="0 = retry dead ends until routed")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--device", default="GPU")
    ap.add_argument("--big-label-scale", type=float, default=1.4)
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    {"route": cmd_route, "render": cmd_render, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
