@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio - High Quality Story Images ===
echo.
echo This installs FLUX.2 Klein 4B FP8 for stronger Roblox character/reference consistency.
echo It is a large local model download.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_story_image_models.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Story image setup failed. Read the error above.
  pause
  exit /b 1
)
echo.
pause
