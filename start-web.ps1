<#
.SYNOPSIS
  Start the Signalyser web UI in the foreground (Ctrl+C stops it cleanly).
.EXAMPLE
  .\start-web.ps1
  .\start-web.ps1 -Port 8001 -NoBrowser
#>
param(
  [int]$Port = 8000,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
  Write-Error "venv Python not found at $py. Run setup first (see README)."
  exit 1
}

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
  Write-Warning "Port $Port is already in use. Stop it first:  .\stop-web.ps1 -Port $Port   (or pick another -Port)"
  exit 1
}

# Open the browser once the server is actually serving (avoids a connection-refused flash).
if (-not $NoBrowser) {
  Start-Job -ScriptBlock {
    param($p)
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Milliseconds 400
      try {
        if ((Invoke-WebRequest "http://127.0.0.1:$p/tools" -UseBasicParsing -TimeoutSec 1).StatusCode -eq 200) {
          Start-Process "http://127.0.0.1:$p/tools"; break
        }
      } catch { }
    }
  } -ArgumentList $Port | Out-Null
}

Write-Host "Signalyser web -> http://127.0.0.1:$Port   (Ctrl+C to stop)" -ForegroundColor Yellow
& $py -m signalyser_web --host 127.0.0.1 --port $Port
