param([string]$Version = '2.3.0')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root 'release-dist'
New-Item -ItemType Directory -Path $out -Force | Out-Null
& python (Join-Path $PSScriptRoot 'build_installers.py')
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
& python (Join-Path $PSScriptRoot 'release_archives.py') --version $Version
if ($LASTEXITCODE -ne 0) { throw 'Archive packaging failed' }
$apkSrc = Join-Path $root 'pc-phone-remote-android\app\build\outputs\apk\release\app-release.apk'
if (Test-Path $apkSrc) {
    Copy-Item $apkSrc -Destination (Join-Path $out "PCPhoneRemote-v$Version.apk") -Force
}
$names = @('PCPhoneRemote-Setup.exe','PCPhoneRemote-Linux-Installer.run',"PCPhoneRemote-Windows-v$Version.zip","PCPhoneRemote-Relay-v$Version.zip","PCPhoneRemote-iOS-Source-v$Version.zip","PCPhoneRemote-v$Version.apk")
$names | Where-Object { Test-Path (Join-Path $out $_) } | ForEach-Object {
    '{0}  {1}' -f (Get-FileHash (Join-Path $out $_) -Algorithm SHA256).Hash.ToLowerInvariant(),$_
} | Set-Content (Join-Path $out 'SHA256SUMS.txt') -Encoding ascii
