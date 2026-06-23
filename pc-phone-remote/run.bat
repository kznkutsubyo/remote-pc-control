@echo off
setlocal
cd /d "%~dp0"
if "%REMOTE_PIN%"=="" (
  echo Set REMOTE_PIN before starting the server.
  exit /b 2
)
python app.py --host 0.0.0.0 --port 8765 --pin %REMOTE_PIN%
pause
