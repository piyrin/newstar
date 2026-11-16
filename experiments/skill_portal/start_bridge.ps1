$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = Join-Path $repo '.venv/Scripts/python.exe'
$bridge = Join-Path $PSScriptRoot 'bridge.py'
$runtime = Join-Path $repo 'airflow/resume_workspace/skill_experiments'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$statusFile = Join-Path $runtime 'bridge.json'
if (Test-Path -LiteralPath $statusFile) {
    $status = Get-Content -LiteralPath $statusFile -Raw | ConvertFrom-Json
    if ((([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) - $status.heartbeat) -lt 20 -and (Get-Process -Id $status.pid -ErrorAction SilentlyContinue)) {
        Write-Output 'Skill execution bridge is already online.'
        return
    }
}
Start-Process -FilePath $python -ArgumentList @('-u', $bridge) -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'bridge-stdout.log') -RedirectStandardError (Join-Path $runtime 'bridge-stderr.log')
