# Requires elevation (Run as Administrator).
# Unregisters PhoneUnlockProvider.dll and stops/removes PhoneUnlockService.exe.
$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Run uninstall-unlock.ps1 from an Administrator PowerShell prompt."
}

$installDir = Join-Path $env:ProgramFiles 'PCPhoneRemote\unlock'
$dllDest = Join-Path $installDir 'PhoneUnlockProvider.dll'
$svcDest = Join-Path $installDir 'PhoneUnlockService.exe'

if (Test-Path -LiteralPath $dllDest) {
    & regsvr32.exe /u /s $dllDest
} else {
    Remove-Item -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}' -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path 'Registry::HKEY_CLASSES_ROOT\CLSID\{D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}' -Recurse -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $svcDest) {
    & $svcDest --uninstall
}

Write-Host "PC Phone Remote Windows Unlock unregistered and service removed."
