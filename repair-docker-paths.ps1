# Run in your own Windows PowerShell. Safe to run again after interruption.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-junction-tools.ps1')
$migration = @(
    @{ Source = 'C:\Users\piyrin\AppData\Local\Programs\DockerDesktop'; Destination = 'D:\docker\anzhuang\DockerDesktop' },
    @{ Source = 'C:\Users\piyrin\AppData\Local\Docker'; Destination = 'D:\docker\huancun\local' },
    @{ Source = 'C:\Users\piyrin\AppData\Roaming\Docker'; Destination = 'D:\docker\config\Docker' },
    @{ Source = 'C:\Users\piyrin\AppData\Roaming\Docker Desktop'; Destination = 'D:\docker\huancun\desktop' }
)
$running = @(Get-Process -Name 'Docker Desktop','com.docker.backend','com.docker.build','docker-agent' -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw 'Please quit Docker Desktop from its tray menu and run this script again. No directories have been changed.'
}

foreach ($entry in $migration) {
    $source = [IO.Path]::GetFullPath($entry.Source)
    $destination = [IO.Path]::GetFullPath($entry.Destination)
    $allowedSources = @(
        'C:\Users\piyrin\AppData\Local\Programs\DockerDesktop',
        'C:\Users\piyrin\AppData\Local\Docker',
        'C:\Users\piyrin\AppData\Roaming\Docker',
        'C:\Users\piyrin\AppData\Roaming\Docker Desktop'
    )
    if ($source -notin $allowedSources -or -not $destination.StartsWith('D:\docker\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Unexpected path in migration record.'
    }
    $item = Get-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
    $backup = $null
    if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        $target = [string](@($item.Target)[0])
        if ($target -and [IO.Path]::GetFullPath($target).TrimEnd('\') -ieq $destination.TrimEnd('\')) {
            Write-Host "Already correct: $source -> $destination"
            continue
        }
        if (-not (Test-Path -LiteralPath $destination -PathType Container) -or
            @(Get-ChildItem -LiteralPath $destination -Force).Count -eq 0) {
            throw "D drive copy missing or empty. Existing link retained: $source"
        }
        Remove-DockerJunctionOnly -LiteralPath $source
    } elseif ($item) {
        if (-not $item.PSIsContainer) { throw "Unexpected file at $source" }
        # Copy the actual folder visible in this terminal, not a presumed backup.
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        Set-DockerPrivateDirectoryAccess -LiteralPath $destination
        Write-Host "Copying and checking: $source"
        & robocopy.exe $source $destination /E /COPY:DAT /DCOPY:DAT /XJ /SL /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
        if ($LASTEXITCODE -ge 8) { throw "Copy failed; original retained: $source" }
        foreach ($file in @(Get-ChildItem -LiteralPath $source -File -Recurse -Force)) {
            $relative = $file.FullName.Substring($source.Length).TrimStart('\')
            $copied = Join-Path $destination $relative
            if (-not (Test-Path -LiteralPath $copied -PathType Leaf) -or
                (Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $copied).Hash) {
                throw "Copy verification failed; original retained: $source"
            }
        }
        $backup = $source + '.before-d-drive-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        if (Test-Path -LiteralPath $backup) { throw "Backup already exists: $backup" }
        Rename-Item -LiteralPath $source -NewName ([IO.Path]::GetFileName($backup))
        Write-Host "Original backup retained: $backup"
    } else {
        if (-not (Test-Path -LiteralPath $destination -PathType Container)) {
            throw "Neither source nor D drive copy exists: $source"
        }
    }
    try {
        & cmd.exe /d /c "mklink /J `"$source`" `"$destination`""
        if ($LASTEXITCODE -ne 0) { throw 'Junction creation failed.' }
        $probe = Get-Item -LiteralPath $source -Force
        $verifiedTarget = [string](@($probe.Target)[0])
        if (-not $verifiedTarget -or [IO.Path]::GetFullPath($verifiedTarget).TrimEnd('\') -ine $destination.TrimEnd('\')) {
            throw "Junction target could not be verified: $source"
        }
    } catch {
        if ($backup -and -not (Get-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue)) {
            Rename-Item -LiteralPath $backup -NewName ([IO.Path]::GetFileName($source))
        }
        throw "Repair stopped for $source. All D drive data and backups retained. $($_.Exception.Message)"
    }
    Write-Host "Repaired: $source -> $destination"
}

$docker = 'D:\docker\anzhuang\DockerDesktop\resources\bin\docker.exe'
& $docker desktop start --timeout 60
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop failed to start; all original backups are retained.' }
& $docker info --format 'Docker engine: {{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Engine verification failed; all original backups are retained.' }
& $docker compose version
if ($LASTEXITCODE -ne 0) { throw 'Compose verification failed.' }
Write-Host 'SUCCESS: Docker paths repaired and engine verified. Backups have NOT been deleted.'
