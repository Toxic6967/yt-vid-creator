@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio - Natural Voice Upgrade ===
echo.
echo Installs the stronger local Story narrator under E:\auto yt.
echo The app will keep Kokoro as a fallback.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_chatterbox_voice.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Natural voice upgrade failed. Read the message above.
  pause
  exit /b 1
)
echo.
pause
