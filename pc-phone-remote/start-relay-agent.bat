@echo off
setlocal
cd /d "%~dp0"
if "%RELAY_URL%"=="" (
  echo Set RELAY_URL first, for example:
  echo setx RELAY_URL https://your-relay.example.com
  exit /b 2
)
if "%RELAY_AGENT_TOKEN%"=="" (
  echo Set RELAY_AGENT_TOKEN first.
  exit /b 2
)
python relay_agent.py --relay-url "%RELAY_URL%" --agent-token "%RELAY_AGENT_TOKEN%"
