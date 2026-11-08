param(
    [switch]$RunTests
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildDir = Join-Path $root 'build'
New-Item -ItemType Directory -Force $buildDir | Out-Null

# Locate either standard VS Build Tools or Portable MSVC in D:\Tools\msvc\msvc
$setupBat = 'D:\Tools\msvc\msvc\setup_x64.bat'
if (-not (Test-Path -LiteralPath $setupBat)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $vsPath = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($vsPath) {
            $setupBat = Join-Path $vsPath 'VC\Auxiliary\Build\vcvars64.bat'
        }
    }
}
if (-not (Test-Path -LiteralPath $setupBat)) {
    throw "MSVC x64 environment script not found."
}

$cmd = @"
call "$setupBat" >nul
if errorlevel 1 exit /b 1
pushd "$buildDir"

echo [1/3] Building PhoneUnlockProvider.dll (Credential Provider v2)...
cl /nologo /utf-8 /std:c++17 /EHsc /O2 /W3 /DUNICODE /D_UNICODE /LD ^
    "$root\src\provider\provider.cpp" ^
    "$root\src\common\ipc.cpp" ^
    "$root\src\common\crypto.cpp" ^
    /link /DEF:"$root\src\provider\PhoneUnlockProvider.def" /OUT:"$buildDir\PhoneUnlockProvider.dll"
if errorlevel 1 exit /b 1

echo [2/3] Building PhoneUnlockService.exe (LocalSystem Unlock Service)...
cl /nologo /utf-8 /std:c++17 /EHsc /O2 /W3 /DUNICODE /D_UNICODE ^
    "$root\src\service\main.cpp" ^
    "$root\src\service\unlock_engine.cpp" ^
    "$root\src\common\ipc.cpp" ^
    "$root\src\common\crypto.cpp" ^
    /link /OUT:"$buildDir\PhoneUnlockService.exe"
if errorlevel 1 exit /b 1

echo [3/3] Building PhoneUnlockSelfTest.exe...
cl /nologo /utf-8 /std:c++17 /EHsc /O2 /W3 /DUNICODE /D_UNICODE ^
    "$root\src\tests\selftest.cpp" ^
    "$root\src\provider\provider.cpp" ^
    "$root\src\service\unlock_engine.cpp" ^
    "$root\src\common\ipc.cpp" ^
    "$root\src\common\crypto.cpp" ^
    /link /OUT:"$buildDir\PhoneUnlockSelfTest.exe"
if errorlevel 1 exit /b 1

popd
"@

$batFile = Join-Path $buildDir 'compile.bat'
Set-Content -LiteralPath $batFile -Value $cmd -Encoding ASCII
& cmd.exe /c $batFile
if ($LASTEXITCODE -ne 0) {
    throw "Native build failed with exit code $LASTEXITCODE"
}

if ($RunTests) {
    & "$buildDir\PhoneUnlockSelfTest.exe"
    if ($LASTEXITCODE -ne 0) {
        throw "Native self-test failed with exit code $LASTEXITCODE"
    }
}
