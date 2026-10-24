# Meldungen der Testmaschine (Windows-PC) an den Test-Hub (Dashboard /admin/testhub/).
# Token nur lokal in $HOME\.vd-testhub-token, auf dem Server nur sein SHA-256 (testhub/tokens.json -> Geraet "windows").
#
#   .\vd-testhub.ps1 beat "bereit"
#   .\vd-testhub.ps1 start "Kombi-Test 0.6.34" [-Kind test]
#   .\vd-testhub.ps1 log "Zeile"
#   .\vd-testhub.ps1 step <key> <todo|active|done|error> "Label" ["Detail"]
#   .\vd-testhub.ps1 progress <done> <total> ["Pruefungen"]
#   .\vd-testhub.ps1 find <fail|warn|crash|pass> "Fundstelle" "Meldung"
#   .\vd-testhub.ps1 end <fertig|abgebrochen|fehler> ["Zusammenfassung"]
param([Parameter(Position = 0, Mandatory = $true)][string]$Cmd,
      [Parameter(Position = 1)][string]$A1 = "", [Parameter(Position = 2)][string]$A2 = "",
      [Parameter(Position = 3)][string]$A3 = "", [Parameter(Position = 4)][string]$A4 = "",
      [string]$Kind = "test")
$ErrorActionPreference = "Stop"
$url = if ($env:VD_TESTHUB_URL) { $env:VD_TESTHUB_URL } else { "https://mc-void-draconic.bresqwik.org/api/testhub/push" }
$token = (Get-Content -Raw (Join-Path $HOME ".vd-testhub-token")).Trim()
$stateFile = Join-Path $env:TEMP "vd-testhub-phases.json"
$t = Get-Date -Format "HH:mm:ss"

function Send($obj) {
    $json = $obj | ConvertTo-Json -Depth 8 -Compress
    Invoke-RestMethod -Uri $url -Method Post -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 15 | Out-Null
}

switch ($Cmd) {
    "beat"     { Send @{ heartbeat = $true; device_state = $(if ($A1) { $A1 } else { "bereit" }) } }
    "start"    { "[]" | Set-Content -Encoding utf8 $stateFile
                 Send @{ reset = $true; status = "läuft"; title = $A1; kind = $Kind; log_append = @("$t Start: $A1") } }
    "log"      { Send @{ log_append = @("$t $A1") } }
    "step"     { $ph = @(); if (Test-Path $stateFile) { $ph = @(Get-Content -Raw $stateFile | ConvertFrom-Json) }
                 $found = $false
                 foreach ($p in $ph) { if ($p.key -eq $A1) { $p.state = $A2; $p.label = $(if ($A3) { $A3 } else { $A1 }); if ($A4) { $p | Add-Member -Force detail $A4 }; $found = $true } }
                 if (-not $found) { $n = [ordered]@{ key = $A1; state = $A2; label = $(if ($A3) { $A3 } else { $A1 }) }; if ($A4) { $n.detail = $A4 }; $ph += [pscustomobject]$n }
                 ($ph | ConvertTo-Json -Depth 5 -Compress) | Set-Content -Encoding utf8 $stateFile
                 Send @{ phase = $A1; phases = @($ph) } }
    "progress" { Send @{ progress = @{ done = [int]$A1; total = [int]$A2; label = $(if ($A3) { $A3 } else { "Prüfungen" }) } } }
    "find"     { Send @{ errors_append = @(@{ type = $A1; where = $A2; msg = $A3 }); log_append = @("$t [$A1] ${A2}: $A3") } }
    "end"      { Send @{ status = $A1; summary = $A2; log_append = @("$t Ende: $A1 $A2") } }
    default    { Get-Content $PSCommandPath -TotalCount 11 | Select-Object -Skip 2; exit 1 }
}
