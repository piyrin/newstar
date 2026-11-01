# RemoveDirectoryW unlinks a junction without deleting its target contents.
# https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-removedirectoryw
if (-not ('DockerJunctionNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DockerJunctionNative {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool RemoveDirectoryW(string path);
}
'@
}

function Remove-DockerJunctionOnly {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $item = Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or -not $item.PSIsContainer) {
        throw "Refusing to remove a real directory or file: $LiteralPath"
    }
    if (-not [DockerJunctionNative]::RemoveDirectoryW($item.FullName)) {
        $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "Cannot unlink junction (Windows error $code): $LiteralPath. No recursive deletion was attempted."
    }
}

function Set-DockerPrivateDirectoryAccess {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    # icacls changes only the DACL; do not request SACL/audit privileges.
    $userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $LiteralPath /grant:r "*${userSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /inheritance:r /Q
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot set private destination permissions. Original folder retained: $LiteralPath"
    }
}
