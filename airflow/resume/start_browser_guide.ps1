$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonExe = Join-Path $projectRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Project Python environment is missing.'
}
Start-Process -FilePath $pythonExe -ArgumentList @((Join-Path $PSScriptRoot 'browser_guide.py')) -WorkingDirectory $projectRoot -WindowStyle Hidden
Write-Output 'Local browser guide started. Pending Airflow material forms will open in your default browser.'
