# New set (railway): five 50-cable puzzles with bundles + loose distractor pieces + one 80-cable puzzle.
# toolless / forbidden / code in parallel, then push results.
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\run_codex_bench.ps1" -ItemsDir items_x -Model gpt-6.2-sol -Effort high -Mode all -Repeats 1
& "$PSScriptRoot\push_github.ps1"
Write-Host "Done. Press Enter to close."; Read-Host | Out-Null
