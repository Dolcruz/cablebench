# Creates the private GitHub repo Dolcruz/cablebench (if missing) and pushes this folder.
param([string]$Repo = "Dolcruz/cablebench", [string]$Visibility = "private")
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path ".git")) { git init -b main }
git add -A
git commit -m "cablebench: procedural 3D cable-tracing benchmark, examples and Codex runs" `
    -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" `
    -m "Claude-Session: https://claude.ai/code/session_015c5fPKWcPkhnjqzhZmevmP"
git rev-parse --verify HEAD 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "Commit failed, see the git message above. Nothing pushed." -ForegroundColor Red; exit 1 }
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) { Write-Host "gh CLI not found. Create $Repo on github.com, then: git remote add origin https://github.com/$Repo.git; git push -u origin main"; exit 1 }
gh repo view $Repo 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { gh repo create $Repo --$Visibility }
if (-not (git remote | Select-String origin)) { git remote add origin "https://github.com/$Repo.git" }
git push -u origin main
if ($LASTEXITCODE -ne 0) { Write-Host "Push failed, see the git message above." -ForegroundColor Red; exit 1 }
Write-Host "Pushed to https://github.com/$Repo" -ForegroundColor Green
