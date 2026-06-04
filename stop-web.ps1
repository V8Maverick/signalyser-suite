<#
.SYNOPSIS
  Stop the Signalyser web server — kills whatever is listening on the port plus
  any signalyser_web processes (the venv launcher + its child interpreter).
.EXAMPLE
  .\stop-web.ps1
  .\stop-web.ps1 -Port 8001
#>
param(
  [int]$Port = 8000
)

$killed = 0

# 1) The real server: whatever is LISTENing on the port (catches the child too).
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  if ($_.OwningProcess) {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    $killed++
  }
}

# 2) Sweep any lingering signalyser_web processes (launcher/redirector pair).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*signalyser_web*' } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $killed++
  }

Start-Sleep -Milliseconds 400

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
  Write-Warning "Port $Port still has a listener — check manually with: Get-NetTCPConnection -LocalPort $Port"
} else {
  Write-Host "Signalyser web stopped (killed $killed process(es); port $Port free)." -ForegroundColor Green
}
