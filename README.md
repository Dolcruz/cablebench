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
* `--waypoints 2,4` how wiggly cables are
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

`bench/items/` holds a fixed set (bomb theme, same cable colour) with 5, 10, 20
and 40 cables. `bench/run_codex_bench.ps1` sends each image through
`codex exec` in isolated `CODEX_HOME`s (only `auth.json` is copied; no
AGENTS.md, no custom instructions, no MCP servers, fresh empty working directory
outside any git repo) in three modes:

* `toolless`: `[features] shell_tool = false`, web search and apps off, read-only
  sandbox. The model only sees the attached image.
* `forbidden`: shell on (read-only sandbox, the image also lies in the working
  directory), but the prompt forbids code and opening files. Measures whether the
  model follows the instruction (`commands_run` > 0 means it did not).
* `code`: shell on, workspace-write sandbox, the image is also `puzzle.png` in the
  working directory and the prompt allows analysing it with code.

Answers, raw events, timing, token counts and the number of shell commands are
written to `bench/results/<model>_<effort>_<timestamp>/`.

```powershell
powershell -ExecutionPolicy Bypass -File bench\run_codex_bench.ps1 -Model gpt-6.2-sol -Effort high -Mode all
```

The 40-cable puzzle was routed with slightly relaxed limits (min crossing angle
22 deg, clearance 2.4 r, crossing spacing 3.0 r, fewer waypoints); the strict
defaults did not converge in reasonable time on 2 CPU cores.

`bench/render_gpu.ps1` sets up a local venv with `bpy` and renders on the GPU
(`CABLEBENCH_DEVICE=GPU`, tries OptiX, then CUDA/HIP/Metal/oneAPI).
