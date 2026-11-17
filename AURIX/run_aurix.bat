@echo off
REM Double-click to start AURIX from source (needs the setup in README.md done once).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run the setup steps from README.md first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py
