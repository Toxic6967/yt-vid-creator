@echo off
setlocal
cd /d %~dp0

echo === Shorts Studio V1 Setup ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py^) was not found.
  pause
  exit /b 1
)

if not exist .venv (
  py -m venv .venv
  if errorlevel 1 (
    echo.
    echo ERROR: Could not create the Python virtual environment.
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo.
  echo ERROR: Could not activate .venv.
  pause
  exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo ERROR: pip upgrade failed.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: Python dependency installation failed.
  echo Fix the error above, then run setup_windows.bat again.
  pause
  exit /b 1
)

echo.
echo Python dependencies installed successfully.
echo.
echo Ollama is required for local script/research AI.
echo Model: qwen3:8b
echo Launch Shorts Studio with: py run.py
echo.
pause
