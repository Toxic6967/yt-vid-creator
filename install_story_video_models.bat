@echo off
setlocal
cd /d %~dp0
echo === Shorts Studio - Cinematic Story Video Models ===
echo.
echo This installs the optional higher-quality keyframe-to-video backend.
echo It downloads large model files for local generation.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_story_video_models.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Story video setup failed. Read the error above.
  pause
  exit /b 1
)
echo.
pause
