# Requires elevation (Run as Administrator).
# Installs and starts PhoneUnlockService.exe as a LocalSystem service and registers PhoneUnlockProvider.dll.
$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Run install-unlock.ps1 from an Administrator PowerShell prompt (preferably inside a Windows VM snapshot first)."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildDir = Join-Path $root 'build'
$dllSource = Join-Path $buildDir 'PhoneUnlockProvider.dll'
$svcSource = Join-Path $buildDir 'PhoneUnlockService.exe'

if (-not (Test-Path -LiteralPath $dllSource) -or -not (Test-Path -LiteralPath $svcSource)) {
    & (Join-Path $root 'build.ps1') -RunTests
}

$installDir = Join-Path $env:ProgramFiles 'PCPhoneRemote\unlock'
New-Item -ItemType Directory -Force $installDir | Out-Null

# Stop any running console or service instance of PhoneUnlockService before replacing binaries.
Stop-Service -Name 'PCPhoneRemoteUnlock' -Force -ErrorAction SilentlyContinue
Stop-Process -Name 'PhoneUnlockService' -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 400

# Restrict directory ACL to SYSTEM and Administrators (Read & Execute for Users/LogonUI).
icacls $installDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)RX" | Out-Null

$dllDest = Join-Path $installDir 'PhoneUnlockProvider.dll'
$svcDest = Join-Path $installDir 'PhoneUnlockService.exe'
Copy-Item -LiteralPath $dllSource -Destination $dllDest -Force
Copy-Item -LiteralPath $svcSource -Destination $svcDest -Force

& $svcDest --install
& regsvr32.exe /s $dllDest
Write-Host "PC Phone Remote Windows Unlock installed successfully in $installDir"
