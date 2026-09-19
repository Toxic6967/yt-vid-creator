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
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Python dependencies installed.
echo.
echo NEXT: install Ollama from https://ollama.com/download/windows if you do not have it.
echo Then run: ollama pull qwen3:8b
echo Then launch this project with: py run.py
echo.
pause
