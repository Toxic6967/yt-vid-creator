@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio - Human Voice ===
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_human_voice.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Human voice setup failed. Read the error above.
  pause
  exit /b 1
)
echo.
pause
