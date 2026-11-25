# cablebench

Procedural 3D cable-tracing puzzles for testing how well vision models can follow
cables in an image. Same game every time (left ports, right connectors, one cable
each), many different looks, exact ground truth.

## What you get per item

* `<id>.png` – the rendered puzzle (Blender Cycles)
* `<id>.json` – full metadata: solution, labels, puzzle geometry, crossings,
  projected cable centrelines in pixel coordinates, timing
* `manifest.jsonl` – one line per item with `prompt` and `answer`
  (ready for an eval harness)

## Guarantees (checked for every puzzle, not hoped for)

* every crossing has an angle of at least `--min-angle` degrees (default 25)
* away from crossings, two cables never touch or run alongside each other
  (centre distance >= 2.6 cable radii)
* crossings are at least 3.5 radii apart, so no pile-ups
* bend radius >= 3 cable radii
* at every crossing the upper cable is lifted cleanly over the lower one
  (over/under is random, so cables weave)
* occluders (pliers) are only placed where they hide short stretches without
  any crossing underneath, so the puzzle stays solvable by continuity

## Themes

| theme | look | left labels | right labels |
|---|---|---|---|
| `bomb` | olive board, steel plate, green rubber, LEDs, timer | letters | numbers |
| `railway` | signal box, brass name plates, braided cables, semaphore flags, copper clips | words | numbers |
| `scifi` | white housing, translucent glowing tubes, clips | shape icons | numbers |
| `steampunk` | verdigris panel, copper pipes, brass collars, gauges | shape icons | numbers |
| `synth` | orange retro synth, patch cables with plugs | waveform icons (n <= 8) or letters | numbers |
| `security` | PCB with traces, orange wires | letters | shuffled numbers |

Each theme randomises camera tilt, small details, LED/flag states, clips and
occluders per seed.

## Difficulty knobs

* `--n` number of cables (routing: 24 cables ~30 s; 40 cables needs relaxed limits, see bench/)
* `--color-mode uniform|few|unique` (default `uniform`: all cables look the same)
* `--preset normal|hard` (`hard`: 3 to 6 waypoints, waypoints anywhere on the board so
  cables cross the whole field, deliberate loops, backtracking; routing is slower)
* `--waypoints 2,4` how wiggly cables are (normal preset)
* `--min-angle` smallest allowed crossing angle
* `--no-extras` disables clips and occluders
* `--res WxH|auto` (`auto` scales the image with n)

## Usage

```bash
pip install bpy numpy scipy pillow      # bpy = Blender as a Python module
python generate.py --out data/v1 --n 6,10,16 --count 5 --themes all --res auto --samples 32
python score.py data/v1/manifest.jsonl predictions.jsonl
```

`predictions.jsonl` lines look like `{"id": "...", "answer": {"A": "3", ...}}`
or `{"id": "...", "answer": "<raw model text containing a JSON object>"}`.
`score.py` reports per-cable accuracy and exact-match rate per n and per theme.

Debug: `--debug-overlay` writes `<id>_gt.png` with the true cable paths drawn
on top of the render.

Rendering cost on 2 CPU cores: about 30 s for 960x540 at 12 samples, about
1.5 to 2.5 min for 1600x900 at 24 samples, about 3 min for 16 cables at
1984x1120. GPU Cycles is much faster.

## Layout

```
cablebench/puzzle.py   routing, crossings, over/under heights, labels (no Blender)
cablebench/bl.py       Blender helpers (meshes, materials, lights, camera, projection)
cablebench/themes.py   the six looks
cablebench/render.py   puzzle + theme -> image + metadata
generate.py            dataset CLI
score.py               scoring
```

## Codex benchmark (bench/)

`bench/run_bench.py` sends each image through `codex exec`, one isolated `CODEX_HOME` per run
(only `auth.json` is copied, fresh empty working folder outside any git repo, neutral random names).
Each home gets a patched copy of the live model catalog (`model_catalog_json`) and a config that
switches off what the mode does not need. Before anything starts, every mode is rendered with
`codex debug prompt-input` and checked by `bench/probe_isolation.py`; the run aborts if the model would
see more than intended. Modes:

* `single`: no tools at all, the image is attached once. Exactly one model request.
* `look`: only `view_image` (it takes a path, so the model can re-read the attached image).
* `code`: the model's native tools minus sub-agents, image generation, goals and skills
  (JavaScript `exec` cell with shell, `view_image`, `apply_patch`); `puzzle.png` in the working folder.
* `forbidden`: same tools and files as `code`, but the prompt forbids using them. Measures whether the
  model follows the instruction (tool calls despite the ban), not what the tools add.

In every mode: no skills, no AGENTS.md, no MCP servers, reasoning summaries on.
`--abstain-prompt` adds a sentence that explicitly allows `null` for cables the model cannot determine.

```powershell
python bench/run_bench.py --items-dir items_x --modes single,code,forbidden --timeout-min 120
python bench/run_bench.py --items-dir items_x --resume bench/results/<run> --recover   # finish crashed runs
```

The repo results folder gets answers, sanitised per-run stats and the score files. Full traces
(rollouts with every tool call and reasoning summary, events, a zip of the working folder) go to a
private folder outside the repo (`%USERPROFILE%/cablebench-traces`).

`score.py` scores every cable as correct, wrong or abstained and gives each run with abstentions a
reason: `honest_unknown`, `broken_output`, `technical` or `refusal` (rules, then optionally an LLM judge
with `--judge gpt-6-luna`). Metrics: accuracy, coverage, precision on answered cables, abstain rate and
`penalized = (correct - wrong) / n`.

`bench/make_grid.py` builds larger sets (cable count x difficulty level, k items per cell) in two
phases, `route` (CPU, parallel, retries on a new seed) and `render` (Blender, GPU), with a secret salt
kept outside the repo. Sets with solutions are written outside the repo (`%USERPROFILE%/cablebench-data`).

Runs 1 to 3 used the older `bench/run_codex_bench.ps1`; its "toolless" mode was not tool-free (see
`bench/RESULTS.md`).

`bench/render_gpu.ps1` sets up a local venv with `bpy` and renders on the GPU
(`CABLEBENCH_DEVICE=GPU`, tries OptiX, then CUDA/HIP/Metal/oneAPI).
