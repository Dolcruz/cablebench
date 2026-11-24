# One click: Codex benchmark (gpt-6.2-sol, high, isolated) -> results -> push to GitHub (private).
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\run_codex_bench.ps1" -Model gpt-6.2-sol -Effort high -Mode all -Repeats 1
& "$PSScriptRoot\push_github.ps1"
Write-Host "Done. Press Enter to close."; Read-Host | Out-Null
