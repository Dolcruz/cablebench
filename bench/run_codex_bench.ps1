# Runs the cable puzzles in bench\items through the Codex CLI in isolated CODEX_HOMEs
# (no custom instructions, no AGENTS.md, no MCP servers), scores the answers and
# writes everything to bench\results\<model>_<effort>_<timestamp>\.
#
# Three modes:
#   toolless : shell tool, web search and apps switched off in the config. Pure vision.
#   forbidden: shell stays on (read-only sandbox, image also in the working folder as puzzle.png),
#              but the prompt forbids code. Tests whether the model sticks to the instruction.
#   code     : shell on, workspace-write sandbox, the image lies in the working folder
#              as puzzle.png and the model may analyse it with code.
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File bench\run_codex_bench.ps1
#   powershell -ExecutionPolicy Bypass -File bench\run_codex_bench.ps1 -Model gpt-6.2-sol -Effort high -Mode both -Repeats 1
param(
    [string]$Model = "gpt-6.2-sol",
    [string]$Effort = "high",
    [ValidateSet("all", "both", "toolless", "forbidden", "code")][string]$Mode = "all",
    [int]$Repeats = 1,
    [string]$Items = "",          # optional comma list of ids, default: all
    [int]$TimeoutMin = 90,
    [string]$ItemsDir = "items",  # folder under bench\ with manifest.jsonl + images
    [string]$WinSandbox = "unelevated"  # Windows sandbox for forbidden/code (elevated needs admin setup)
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = $utf8
[Console]::OutputEncoding = $utf8

$itemsName = $ItemsDir
$itemsDir = Join-Path $PSScriptRoot $itemsName
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$resDir = Join-Path $PSScriptRoot "results\$($itemsName)_$($Model)_$($Effort)_$stamp"
New-Item -ItemType Directory -Force -Path $resDir | Out-Null

$mainHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$mainAuth = Join-Path $mainHome "auth.json"
if (-not (Test-Path $mainAuth)) { throw "No auth.json in $mainHome (codex login first)" }
$mainCfg = Join-Path $mainHome "config.toml"
if (Test-Path $mainCfg) {
    $m = Select-String -Path $mainCfg -Pattern '^\s*model\s*=' | Select-Object -First 1
    if ($m) { Write-Host "Your normal config uses: $($m.Line.Trim())  (this run uses model = $Model)" }
}

# ---------------------------------------------------------------- isolated codex homes
$run = "C:\cbrun"
New-Item -ItemType Directory -Force -Path $run | Out-Null
Get-ChildItem $run -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$modes = switch ($Mode) { "all" { @("toolless", "forbidden", "code") } "both" { @("toolless", "code") } default { @($Mode) } }
$homes = @{}
foreach ($md in $modes) {
    $h = Join-Path $run "codex_home_$md"
    New-Item -ItemType Directory -Force -Path $h | Out-Null
    Copy-Item $mainAuth (Join-Path $h "auth.json") -Force
    if ($md -eq "toolless") {
        $cfg = @"
model = "$Model"
model_reasoning_effort = "$Effort"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"

[features]
shell_tool = false
unified_exec = false
apps = false
"@
    } elseif ($md -eq "forbidden") {
        $cfg = @"
model = "$Model"
model_reasoning_effort = "$Effort"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"

[features]
apps = false

[windows]
sandbox = "$WinSandbox"
"@
    } else {
        $cfg = @"
model = "$Model"
model_reasoning_effort = "$Effort"
approval_policy = "never"
sandbox_mode = "workspace-write"
web_search = "disabled"

[features]
apps = false

[windows]
sandbox = "$WinSandbox"
"@
    }
    $cfg | Set-Content -Encoding UTF8 (Join-Path $h "config.toml")
    $homes[$md] = $h
}
$authHashBefore = (Get-FileHash $mainAuth).Hash
Write-Host "Isolated CODEX_HOMEs under $run (no AGENTS.md, no MCP, no custom instructions). Modes: $($modes -join ', ')"

$codex = (Get-Command codex -ErrorAction Stop).Source
$codexVersion = "$(& $codex --version)"
Write-Host "codex: $codex  ($codexVersion)"
if ($homes.ContainsKey("toolless")) {
    $env:CODEX_HOME = $homes["toolless"]
    $feat = & $codex features list 2>&1 | Out-String
    Remove-Item Env:CODEX_HOME
    $line = ($feat -split "`n") | Where-Object { $_ -match '^\s*shell_tool\b' }
    if ($line -and $line -match 'false') { Write-Host "toolless check: $($line.Trim())" -ForegroundColor Green }
    else { Write-Host "WARNING: could not confirm shell_tool=false in the toolless home ($($line))" -ForegroundColor Yellow }
}

# ---------------------------------------------------------------- prompts
$tailToolless = "`n`nLook at the attached image and answer from the image alone."
$tailForbidden = "`n`nLook at the attached image and answer from the image alone. Do not run any shell commands, scripts or code, and do not open any files."
$tailCode = "`n`nThe same image is also saved as puzzle.png in the current working directory. " +
            "You may write and run code (for example Python) to analyse it if that helps. Do not look for or open any other files."

# ---------------------------------------------------------------- run
$manifest = Get-Content (Join-Path $itemsDir "manifest.jsonl") | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
if ($Items) { $want = $Items.Split(","); $manifest = $manifest | Where-Object { $want -contains $_.id } }

# ---------------------------------------------------------------- phase 1: start every run in parallel
$tasks = @()
foreach ($it in $manifest) {
    foreach ($md in $modes) {
        for ($rep = 1; $rep -le $Repeats; $rep++) {
            $tag = "$($it.id)_$($md)_r$rep"
            # own CODEX_HOME per run (parallel sessions must not share one), same config as the mode
            # neutral random names: nothing the model can see (cwd, image path, warnings) may contain the item id or seed
            $rid = [guid]::NewGuid().ToString("N").Substring(0, 10)
            $h = Join-Path $run "h_$rid"
            if (Test-Path $h) { Remove-Item $h -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $h | Out-Null
            Copy-Item (Join-Path $homes[$md] "config.toml") (Join-Path $h "config.toml") -Force
            Copy-Item $mainAuth (Join-Path $h "auth.json") -Force
            # fresh, empty working folder per run, outside any git repo
            $work = Join-Path $run "w_$rid"
            if (Test-Path $work) { Remove-Item $work -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $work | Out-Null
            $imgDir = Join-Path $run "i_$rid"
            New-Item -ItemType Directory -Force -Path $imgDir | Out-Null
            $img = Join-Path $imgDir "puzzle.png"
            Copy-Item (Join-Path $itemsDir $it.image) $img -Force
            if ($md -ne "toolless") { Copy-Item $img (Join-Path $work "puzzle.png") -Force }
            $jsonl = Join-Path $resDir "$tag.events.jsonl"
            $last = Join-Path $resDir "$tag.answer.txt"
            $timeFile = Join-Path $resDir "$tag.seconds.txt"
            $prompt = $it.prompt + $(switch ($md) { "code" { $tailCode } "forbidden" { $tailForbidden } default { $tailToolless } })
            $sandbox = if ($md -eq "code") { "workspace-write" } else { "read-only" }
            $job = Start-Job -ScriptBlock {
                param($codex, $img, $work, $jsonl, $last, $prompt, $Model, $home2, $sandbox, $timeFile)
                $env:CODEX_HOME = $home2
                $OutputEncoding = New-Object System.Text.UTF8Encoding $false
                $sw = [Diagnostics.Stopwatch]::StartNew()
                $prompt | & $codex exec --image "$img" --skip-git-repo-check --json -C "$work" -m $Model `
                    -s $sandbox --output-last-message "$last" - 2>&1 | Out-File -Encoding UTF8 $jsonl
                $sw.Stop()
                "$([math]::Round($sw.Elapsed.TotalSeconds, 1))" | Set-Content $timeFile
            } -ArgumentList $codex, $img, $work, $jsonl, $last, $prompt, $Model, $h, $sandbox, $timeFile
            $tasks += [pscustomobject]@{ it = $it; md = $md; rep = $rep; tag = $tag; job = $job; home = $h
                                         jsonl = $jsonl; last = $last; timeFile = $timeFile }
            Write-Host "started $tag ($($it.n_cables) cables)"
        }
    }
}
$homesAll = @($tasks | ForEach-Object { $_.home })

# ---------------------------------------------------------------- phase 2: wait, show progress
$deadline = (Get-Date).AddMinutes($TimeoutMin)
$t0 = Get-Date
while ($true) {
    $running = @($tasks | Where-Object { $_.job.State -eq "Running" })
    $finished = $tasks.Count - $running.Count
    Write-Host ("[{0:hh\:mm\:ss}] {1}/{2} finished, still running: {3}" -f ((Get-Date) - $t0), $finished, $tasks.Count,
        (($running | ForEach-Object { $_.tag }) -join ", "))
    if ($running.Count -eq 0) { break }
    if ((Get-Date) -gt $deadline) {
        foreach ($t in $running) { Stop-Job $t.job; Write-Host "TIMEOUT $($t.tag)" -ForegroundColor Red }
        break
    }
    Start-Sleep -Seconds 30
}

# ---------------------------------------------------------------- phase 3: score
$summary = @()
$preds = @()
foreach ($t in $tasks) {
    $it = $t.it; $md = $t.md; $rep = $t.rep
    $timedOut = $t.job.State -ne "Completed"
    Receive-Job $t.job -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $t.job -Force
    $secs = if (Test-Path $t.timeFile) { [double](Get-Content $t.timeFile) } else { $null }
    $answerText = if (Test-Path $t.last) { Get-Content $t.last -Raw } else { "" }
    $events = if (Test-Path $t.jsonl) { Get-Content $t.jsonl } else { @() }
    $cmdCount = ($events | Where-Object { $_ -match 'command_execution' -and $_ -match 'item\.completed' } | Measure-Object).Count
    $cmdRejected = ($events | Where-Object { $_ -match 'exec_command failed' } | Measure-Object).Count
    $refused = ($answerText -match "(?i)can.?t provide|cannot provide|can.?t help|won.?t provide|explosive")
    $inTok = $null; $outTok = $null; $reasonTok = $null
    foreach ($e in $events) {
        if ($e -match '"usage"') {
            try {
                $u = ($e | ConvertFrom-Json).usage
                if ($u) { $inTok = $u.input_tokens; $outTok = $u.output_tokens; $reasonTok = $u.reasoning_output_tokens }
            } catch {}
        }
    }
    $pred = @{}
    $mm = [regex]::Match($answerText, '\{[\s\S]*\}')
    if ($mm.Success) {
        try { ($mm.Value | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $pred[$_.Name.Trim()] = "$($_.Value)".Trim() } } catch {}
    }
    $ok = 0; $total = 0; $wrong = @()
    foreach ($p in $it.answer.PSObject.Properties) {
        $total++
        if ($pred.ContainsKey($p.Name) -and $pred[$p.Name].ToLower() -eq "$($p.Value)".ToLower()) { $ok++ }
        else { $wrong += "$($p.Name):$($pred[$p.Name])!=$($p.Value)" }
    }
    $row = [ordered]@{
        id = $it.id; mode = $md; repeat = $rep; n_cables = $it.n_cables; n_crossings = $it.n_crossings
        correct = $ok; total = $total; accuracy = [math]::Round($ok / [math]::Max($total, 1), 3); exact = ($ok -eq $total)
        seconds = $secs; timed_out = $timedOut; commands_run = $cmdCount; commands_rejected = $cmdRejected; refused = $refused
        input_tokens = $inTok; output_tokens = $outTok; reasoning_tokens = $reasonTok
        wrong = ($wrong -join " ")
    }
    $summary += [pscustomobject]$row
    $preds += (@{ id = $it.id; mode = $md; repeat = $rep; answer = $answerText } | ConvertTo-Json -Compress)
    if ($md -eq "toolless" -and $cmdCount -gt 0) { Write-Host "WARNING: $($t.tag) ran commands although the shell tool was disabled" -ForegroundColor Yellow }
    if ($md -eq "forbidden" -and ($cmdCount + $cmdRejected) -gt 0) { Write-Host "NOTE: $($t.tag) ran $cmdCount command(s) although the prompt forbade it" -ForegroundColor Yellow }
}

# auth may have been refreshed inside an isolated home: copy the newest one back so the main login stays valid
$changed = (@($homes.Values) + $homesAll) | ForEach-Object { Join-Path $_ "auth.json" } | Where-Object { Test-Path $_ } |
    Where-Object { (Get-FileHash $_).Hash -ne $authHashBefore } |
    Sort-Object { (Get-Item $_).LastWriteTime } -Descending | Select-Object -First 1
if ($changed -and (Get-FileHash $mainAuth).Hash -eq $authHashBefore) {
    Copy-Item $changed $mainAuth -Force
    Write-Host "Refreshed auth.json copied back to $mainHome"
}
foreach ($h in (@($homes.Values) + $homesAll)) { Remove-Item (Join-Path $h "auth.json") -Force -ErrorAction SilentlyContinue }

$preds | Set-Content -Encoding UTF8 (Join-Path $resDir "predictions.jsonl")
$summary | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $resDir "summary.json")
$summary | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $resDir "summary.csv")
@{ model = $Model; effort = $Effort; modes = $modes; repeats = $Repeats; codex_version = $codexVersion; started = $stamp } |
    ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $resDir "run.json")
Write-Host ""
$summary | Format-Table id, mode, correct, total, exact, seconds, commands_run, commands_rejected, refused, reasoning_tokens -AutoSize
Write-Host "Results: $resDir"
