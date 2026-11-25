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

## Run 3: items_x, gpt-6.2-sol, effort high (2026-11-24)

Five 50-cable puzzles (a/b/c: calm + 4 bundles + 5 loose pieces, d/e: hard + 2 bundles + 5 loose) and one
calm 80-cable puzzle. Correct / wrong / abstained (null) per cable, scored with the new `score.py`:

| item | old "toolless" | forbidden | code |
|---|---|---|---|
| 50 a | 42 / 8 / 0 | 7 / 43 / 0 | 35 / 15 / 0 |
| 50 b | 13 / 2 / 35 | 7 / 43 / 0 | 6 / 44 / 0 |
| 50 c | 22 / 28 / 0 | 2 / 27 / 21 | 0 / 2 / 48 |
| 50 d | 3 / 2 / 45 | 1 / 6 / 43 | 10 / 40 / 0 |
| 50 e | 19 / 31 / 0 | 3 / 47 / 0 | 22 / 28 / 0 |
| 80 a | 51 / 29 / 0 | 0 / 2 / 78 | 29 / 51 / 0 |

Every abstention in run 3 is an explicit `null` in otherwise complete JSON. Rules and the LLM judge
(gpt-6-luna, effort low) agree on all six runs with abstentions: `honest_unknown`. Two of them were
checked by hand (80 a forbidden: 78 null, only H and L answered; 50 d old toolless: the model wrote
"Some crossings still give conflicting traces" and then left 45 labels null). The "Reconnecting... 5/5"
events in those runs are the WebSocket-to-HTTPS fallback at the start; every run still completed its turn.
The old scorer counted null as wrong; the correct counts above are unchanged.

## Measurement problems found on 2026-11-25 (affect runs 1 to 3)

**Old "toolless" was a JavaScript code mode, not pure vision.** The model catalog of codex-cli 0.171/0.172
sets `tool_mode = "code_mode_only"` for gpt-6.2-sol. With `shell_tool = false` the model still had a
JavaScript `exec` cell (V8 isolate, no file system, no network) with nested tools (`view_image`,
`apply_patch`, MCP resource tools, clock) plus sub-agent tools (`spawn_agent`, ...). In the two old
toolless rollouts that survived (80 a: 75 `exec` cells, 50 c: 92), the model called `view_image` once or
twice to get the PNG as a base64 data URL, decoded it in JavaScript and ran its own pixel-level tracing
(ridge following, flow, coverage). That is where the 3 to 12 million input tokens came from. It was not a
`view_image` loop. Only these two runs have full rollouts; for the other old toolless runs the token
counts point the same way but the calls cannot be shown anymore. Old "toolless" is therefore best read as
**code without shell** (labelled `js_noshell` in the new score files), not as `look`.

**Skills and the user's home path were visible in every isolated run.** The developer prompt listed
13 skills (9 host skills from `~/.agents/skills`, 4 Codex system skills) with the absolute path of the
user's home. In 80 a toolless the model opened `verify-project/SKILL.md`. Run 3 started before the
`[[skills.config]]` switch was committed.

**Old "forbidden" was close to single-shot** (20k to 50k tokens, one request), but it had the same tool
set as code; it is kept as the instruction-following mode.

## New harness (`bench/run_bench.py`, 2026-11-25)

Each run gets its own CODEX_HOME with a patched copy of the live model catalog (`model_catalog_json`)
and switches off everything the mode does not need. Before a run starts, every mode is rendered with
`codex debug prompt-input` and checked by `bench/probe_isolation.py`; the run aborts if the model would
see more than intended. After each run the real rollout is analysed again (requests, tool calls,
nested JavaScript tool calls, reasoning summaries, every file path the model touched).

| mode | what the model sees (verified with probe and rollouts) |
|---|---|
| `single` | no tools at all, image attached once (3840x2160, `detail: original`), exactly one request |
| `look` | only `view_image` (it takes a path only, so it can re-read the same full image, nothing else) |
| `code` | native tool set minus sub-agents, image generation, goals, request_user_input, tool search: JS `exec` cell with `exec_command`, `view_image`, `apply_patch`; `puzzle.png` in the working folder |
| `forbidden` | same tools and files as `code`, prompt forbids tools |

In all modes: 0 skills, no AGENTS.md, no MCP servers, no user path in the prompt,
`model_reasoning_summary = "detailed"` (summaries were empty in run 3).

Control runs (railway hard set from run 2, all answers correct):

| item | mode | requests | tool calls | input tokens | old toolless | old forbidden |
|---|---|---:|---|---:|---:|---:|
| 5 | single | 1 | none | 13,104 | 14,677 | 15,554 |
| 5 | look / code / forbidden | 1 each | none | 7,834 / 10,934 / 10,936 | | |
| 20 | single | 1 | none | 15,527 | 344,829 | 17,977 |
| 20 | look | 2 | 1 view_image | 28,178 | | |
| 40 | look | 2 | 1 view_image | 42,056 | 6,846,094 | 23,709 |

Known gap: the sandbox lets `code`/`forbidden` read the whole disk. A `[permissions.filesystem] deny_read`
entry had no visible effect, so instead every path in a tool call is audited and runs that touch the
benchmark (repo, manifests, solution images, salt, traces, other run folders) are flagged `leak_suspect`.

Full traces (rollouts, events, working folders) are kept in a private folder outside this repo; this
repo only gets answers, sanitised per-run stats (`*.stats.json`) and the score files.
