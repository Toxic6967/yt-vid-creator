@echo off
setlocal
cd /d %~dp0
echo ==========================================================
echo Shorts Studio - Story Quality Upgrade
echo ==========================================================
echo.
echo This checks/installs:
echo   1. Kokoro fallback narration
echo   2. Chatterbox natural Story narration
echo   3. FLUX.2 Klein 4B Story keyframes
echo   4. Blender V3 deterministic Roblox R15 animation
echo   5. LTX 2B cinematic keyframe-to-video ^(legacy fallback^)
echo.
echo Existing model files are skipped.
echo Heavy files will be stored under E:\auto yt.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_external_storage.ps1" -Quiet
if errorlevel 1 exit /b 1

call install_human_voice.bat
if errorlevel 1 exit /b 1

call install_natural_voice.bat
if errorlevel 1 exit /b 1

call install_story_image_models.bat
if errorlevel 1 exit /b 1

call install_animation_engine.bat
if errorlevel 1 exit /b 1

call install_story_video_models.bat
if errorlevel 1 exit /b 1

echo.
echo ==========================================================
echo Story quality upgrade complete.
echo Reopen ComfyUI, then run: py run.py
echo Story Studio will now prefer V3 Roblox animation over full generative video.
echo ==========================================================
pause
