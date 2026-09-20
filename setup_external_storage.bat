@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio - Move Storage to E:\auto yt ===
echo.
echo Close Shorts Studio and ComfyUI before continuing.
echo This moves Shorts Studio models/data off C: and registers E:\auto yt with ComfyUI.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_external_storage.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Storage setup failed. Read the message above.
  pause
  exit /b 1
)
echo.
pause
