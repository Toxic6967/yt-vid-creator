@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio - Wan 2.1 Video Models ===
echo.
echo This will download several GB of official ComfyUI Wan 2.1 model files.
echo They are required for genuine local AI video generation.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_wan_video_models.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Wan video setup failed. Read the error above.
  pause
  exit /b 1
)
echo.
pause
