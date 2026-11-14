@echo off
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD if exist "%USERPROFILE%\AppData\Local\Python\bin\python.exe" (
    set "PY_CMD=%USERPROFILE%\AppData\Local\Python\bin\python.exe"
)
if not defined PY_CMD if exist "%USERPROFILE%\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=%USERPROFILE%\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

if not defined PY_CMD (
    echo [ERROR] Python 3 not found. Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Launching PC Phone Remote Pro installer...
%PY_CMD% "%~dp0installer.py" %*
if errorlevel 1 (
    echo.
    echo [ERROR] Installer exited with code %errorlevel%.
    pause
    exit /b %errorlevel%
)
