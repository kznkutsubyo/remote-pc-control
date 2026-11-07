$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root 'release-dist'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$stage = Join-Path $out 'stage'
$pc = Join-Path $stage 'pc-phone-remote'
$native = Join-Path $stage 'windows-unlock'
New-Item -ItemType Directory -Path $pc,$native -Force | Out-Null
Get-ChildItem (Join-Path $root 'pc-phone-remote') -File | Where-Object { $_.Extension -in '.py','.bat','.vbs','.ps1','.html','.md' -or $_.Name -in 'requirements.txt','config.example.json' } | Copy-Item -Destination $pc
Copy-Item (Join-Path $root 'windows-unlock\*.ps1'),(Join-Path $root 'windows-unlock\*.bat'),(Join-Path $root 'windows-unlock\README.md') -Destination $native
New-Item -ItemType Directory -Path (Join-Path $native 'build') -Force | Out-Null
Copy-Item (Join-Path $root 'windows-unlock\build\PhoneUnlockProvider.dll'),(Join-Path $root 'windows-unlock\build\PhoneUnlockService.exe'),(Join-Path $root 'windows-unlock\build\PhoneUnlockSelfTest.exe') -Destination (Join-Path $native 'build')
Copy-Item (Join-Path $root 'LICENSE'),(Join-Path $root 'RELEASE_NOTES.md') -Destination $stage
Compress-Archive -Path "$stage\*" -DestinationPath (Join-Path $out 'PCPhoneRemote-Windows-v2.2.zip') -Force
Compress-Archive -Path "$pc\*" -DestinationPath (Join-Path $out 'PCPhoneRemote-Relay-v2.2.zip') -Force
Copy-Item (Join-Path $root 'pc-phone-remote-android\app\build\outputs\apk\release\app-release.apk') -Destination (Join-Path $out 'PCPhoneRemote-v2.2.apk')
Get-ChildItem $out -File | Where-Object {$_.Extension -in '.zip','.apk'} | ForEach-Object { '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(),$_.Name } | Set-Content (Join-Path $out 'SHA256SUMS.txt') -Encoding ascii
