@echo off
cd /d "%~dp0"
python.exe autostart.py --disable
echo.
echo Auto-start has been disabled.
echo.
pause
