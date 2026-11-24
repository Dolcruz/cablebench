# Hard set (railway theme, hard preset): toolless / forbidden / code in parallel, then push results.
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\run_codex_bench.ps1" -ItemsDir items_hard -Model gpt-6.2-sol -Effort high -Mode all -Repeats 1
& "$PSScriptRoot\push_github.ps1"
Write-Host "Done. Press Enter to close."; Read-Host | Out-Null
