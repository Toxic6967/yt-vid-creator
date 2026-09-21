@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio V5 - Roblox Machinima Engine ===
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_animation_engine.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Animation engine setup failed. Read the message above.
  pause
  exit /b 1
)
echo.
pause
