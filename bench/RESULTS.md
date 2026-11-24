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
