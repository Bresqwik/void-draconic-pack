# Void & Draconic – Test-Instanz starten (Windows)
# Holt den Pack-Stand eines Branches in die Test-Instanz und startet sie mit dem Test-Konto.
# Aufruf:  powershell -ExecutionPolicy Bypass -File vd-test.ps1 [-Branch test] [-World Sandbox] [-NoSync]
param(
    [string]$Branch = "test",
    [string]$World = "Sandbox",
    [string]$Account = "MarkMero",
    [switch]$NoSync
)
$ErrorActionPreference = "Stop"
$prism = "$env:LOCALAPPDATA\Programs\PrismLauncher\prismlauncher.exe"
$inst  = "$env:APPDATA\PrismLauncher\instances\Void-Draconic-Test"
$mc    = "$inst\minecraft"
if (-not (Test-Path $inst)) { throw "Test-Instanz fehlt: $inst (siehe README.md)" }

$running = Get-CimInstance Win32_Process -Filter "Name='javaw.exe'" |
    Where-Object { $_.CommandLine -like "*Void-Draconic-Test*" }
if ($running) { throw "Test-Instanz läuft schon (PID $($running.ProcessId))." }

if (-not $NoSync) {
    $java = (Get-Content "$inst\instance.cfg" | Where-Object { $_ -like "JavaPath=*" }) -replace "^JavaPath=", ""
    $java = $java -replace "javaw\.exe$", "java.exe"
    $url = "https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/$Branch/pack.toml"
    Write-Host "Sync: $url"
    Push-Location $mc
    try { & $java -jar packwiz-installer-bootstrap.jar -g $url; if ($LASTEXITCODE) { throw "packwiz-Fehler $LASTEXITCODE" } }
    finally { Pop-Location }
}

Write-Host "Starte Test-Instanz als $Account, Welt $World"
$launchArgs = @("--launch", "Void-Draconic-Test", "--profile", $Account)
if ($World) { $launchArgs += @("--world", $World) }
Start-Process $prism -ArgumentList $launchArgs
