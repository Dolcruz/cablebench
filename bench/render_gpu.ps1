# Optional: render on the local GPU. Creates .venv with Blender's Python module (bpy needs Python 3.13).
param([string]$Args_ = "--out data\gpu_test --count 1 --n 8 --themes all --res 1600x900 --samples 64")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path ".venv")) {
    if (Get-Command uv -ErrorAction SilentlyContinue) { uv venv --python 3.13 .venv }
    else { py -3.13 -m venv .venv }
    & .venv\Scripts\python.exe -m pip install --upgrade pip
    & .venv\Scripts\python.exe -m pip install bpy==5.3.0 numpy scipy pillow
}
$env:CABLEBENCH_DEVICE = "GPU"
& .venv\Scripts\python.exe generate.py $Args_.Split(" ")
