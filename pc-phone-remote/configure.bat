@echo off
cd /d "%~dp0"
if exist "%~dp0PCPhoneRemote.exe" (
    start "" "%~dp0PCPhoneRemote.exe"
    exit /b 0
)
if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Python\bin\pythonw.exe" "%~dp0configure.py"
    exit /b 0
)
start "" pythonw.exe "%~dp0configure.py"
