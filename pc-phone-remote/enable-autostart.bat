@echo off
cd /d "%~dp0"
python.exe autostart.py --enable
echo.
echo Auto-start has been enabled. PC Phone Remote will start automatically when you log into Windows.
echo.
pause
