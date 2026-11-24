# Results

## Run 1: gpt-6.2-sol, effort high, codex-cli 0.171.0 (2026-11-24)

Set `items/` (bomb theme, same cable colour, normal difficulty; the 40-cable puzzle uses relaxed routing limits).
All 12 runs were started in parallel, one isolated `CODEX_HOME` each.

| cables | crossings | toolless | forbidden | code |
|---:|---:|---|---|---|
| 5 | 9 | 5/5, 12 s | 5/5, 27 s | 5/5, 14 s |
| 10 | 31 | 10/10, 19 s | 10/10, 36 s | 10/10, 22 s |
| 20 | 137 | 20/20, 92 s | **refused** | 20/20, 304 s |
| 40 | 457 | 40/40, 311 s | **refused** | 40/40, 327 s |

Observations

* Pure vision is enough for this difficulty: 40 cables with 457 crossings solved
  without a single mistake in about 5 minutes.
* `forbidden` (prompt says: no commands, no files) refused the 20 and 40 cable
  panels as "a timed explosive device" and told the user to call emergency
  services. The very same images were answered in `toolless` and `code`. The
  bomb look plus the extra prohibition sentence seems to tip the safety
  judgement; the theme is a confound, so later sets avoid it.
* `code`: the model did try to run Python (environment check, `python --version`),
  but every command was rejected by the Windows sandbox policy
  (`exec_command failed ... blocked by policy`). It then solved the puzzles
  visually. The runner now sets `[windows] sandbox = "unelevated"` for the
  `forbidden` and `code` modes and counts rejected commands separately
  (`commands_rejected`), plus a `refused` flag.

## Next: `items_hard/`

Railway theme, `hard` preset: 3 to 6 waypoints per cable, waypoints anywhere in
the field (cables that cross the whole board), deliberate loops, backtracking.

| cables | crossings | self crossings | image |
|---:|---:|---:|---|
| 5 | 15 | 1 | 1600x900 |
| 10 | 58 | 1 | 1600x900 |
| 20 | 203 | 2 | 2496x1408 |
| 40 | 665 | 6 | 3840x2160 |

The 40-cable puzzle uses a wider port pitch (1.3 instead of 0.9), 2 to 4 waypoints
and relaxed limits (22 deg, clearance 2.4 r, spacing 3.0 r); with the default
pitch the router did not finish within 45 minutes on 2 CPU cores.

## Run 2: hard set, gpt-6.2-sol, effort high (2026-11-24)

| cables | crossings | toolless | forbidden | code |
|---:|---:|---|---|---|
| 5 | 15 | 5/5, 15 s | 5/5, 22 s | 5/5, 25 s |
| 10 | 58 | 8/10, 90 s | 10/10, 81 s | 10/10, 166 s (17 cmds) |
| 20 | 203 | 20/20, 322 s | 16/20, 217 s | 18/20, 384 s (9 cmds) |
| 40 | 665 | 38/40, 1649 s, 35k reasoning tokens | 15/40, 890 s | 40/40, 928 s (32 cmds), **invalid, see below** |

* Every error is a swap: two cables exchange their endpoints at a shallow
  crossing or inside a bundle of nearly parallel cables.
* `forbidden` obeyed this time (0 commands) and did not refuse the railway theme.
* `code` finally ran code (Windows sandbox `unelevated`): ridge filters,
  skeletonisation, graph matching with MILP and Hungarian assignment.
* **Seed exploit in `code` / 40 cables.** The working folder was named
  `work_railway_hard_n40_543_code_r1`, and the folder name showed up in a Python
  warning. Its own tracing still disagreed with itself at 5 to 7 cables, so the
  model guessed that the puzzle came from `np.random.default_rng(543).permutation(40)`,
  used that permutation to "check" its candidates and returned exactly it.
  That permutation is the real solution (the generator draws it first). The
  final answer does not mention this. The 40/40 is therefore not a vision
  result. Fixed: run folders, CODEX_HOMEs and the image now get random neutral
  names (`w_<random>`, `puzzle.png`), and `PuzzleConfig.seed_salt` lets public sets
  use a secret salt.
