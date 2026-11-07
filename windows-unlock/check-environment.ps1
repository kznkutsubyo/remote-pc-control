$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$locator = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$compilerInstall = @()
if (Test-Path -LiteralPath $locator) {
    $compilerInstall = @(& $locator -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)
}
$portableMsvc = 'D:\Tools\msvc\msvc\VC\Tools\MSVC'
if ((Test-Path -LiteralPath $portableMsvc) -and $compilerInstall.Count -eq 0) {
    $compilerInstall = @($portableMsvc)
}
$sdkRoots = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Include'),
    'D:\Tools\msvc\msvc\Windows Kits\10\Include'
)
$credentialHeaders = @()
foreach ($sdkRoot in $sdkRoots) {
    if (Test-Path -LiteralPath $sdkRoot) {
        $credentialHeaders += @(Get-ChildItem -LiteralPath $sdkRoot -Filter credentialprovider.h -File -Recurse -ErrorAction SilentlyContinue)
    }
}
$providerDll = Join-Path $root 'build\PhoneUnlockProvider.dll'
$serviceExe = Join-Path $root 'build\PhoneUnlockService.exe'
$regPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}'
[pscustomobject]@{
    CppBuildTools = ($compilerInstall.Count -gt 0)
    CredentialProviderSdk = ($credentialHeaders.Count -gt 0)
    NativePrototypeImplemented = ((Test-Path -LiteralPath $providerDll) -and (Test-Path -LiteralPath $serviceExe))
    WindowsLogonModified = (Test-Path -LiteralPath $regPath)
} | Format-List
