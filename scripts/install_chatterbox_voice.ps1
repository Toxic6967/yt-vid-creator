$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Shorts Studio - Natural Voice Upgrade ===" -ForegroundColor Cyan
Write-Host "Installs an isolated Python 3.11 Chatterbox voice environment on external storage."
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot
$storageMarker = Join-Path $projectRoot ".shorts_studio_storage"
if (Test-Path $storageMarker) {
    $storageRoot = (Get-Content $storageMarker -Raw).Trim()
}
else {
    $storageRoot = "E:\auto yt"
}
if (-not $storageRoot) {
    throw "Storage root is empty. Run setup_external_storage.bat first."
}

$voiceRoot = Join-Path $storageRoot "voice\chatterbox"
$cacheRoot = Join-Path $storageRoot "cache"
$hfCache = Join-Path $cacheRoot "huggingface"
$pipCache = Join-Path $cacheRoot "pip"
New-Item -ItemType Directory -Force -Path $voiceRoot, $hfCache, $pipCache | Out-Null

$env:HF_HOME = $hfCache
$env:HUGGINGFACE_HUB_CACHE = Join-Path $hfCache "hub"
$env:TORCH_HOME = Join-Path $cacheRoot "torch"
$env:PIP_CACHE_DIR = $pipCache

Write-Host "Voice environment: $voiceRoot" -ForegroundColor Green
Write-Host "Model/cache root:  $cacheRoot" -ForegroundColor Green
Write-Host ""

Write-Host "Installing/updating uv bootstrap..." -ForegroundColor Yellow
& py -m pip install --upgrade uv
if ($LASTEXITCODE -ne 0) {
    throw "Could not install uv."
}

$uvExe = (& py -c "import shutil,sysconfig,os; p=shutil.which('uv'); print(p if p else os.path.join(sysconfig.get_path('scripts'),'uv.exe'))").Trim()
if (-not (Test-Path $uvExe)) {
    throw "uv was installed, but uv.exe could not be found."
}
Write-Host "uv: $uvExe" -ForegroundColor Green

Write-Host "Ensuring Python 3.11 is available for Chatterbox..." -ForegroundColor Yellow
& $uvExe python install 3.11
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the isolated Python 3.11 runtime."
}

$venv = Join-Path $voiceRoot ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating isolated Chatterbox environment..." -ForegroundColor Yellow
    & $uvExe venv $venv --python 3.11
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Chatterbox virtual environment."
    }
}

Write-Host "Installing Chatterbox TTS..." -ForegroundColor Yellow
& $uvExe pip install --python $venvPython --upgrade chatterbox-tts
if ($LASTEXITCODE -ne 0) {
    throw "Could not install Chatterbox TTS."
}

Write-Host "Testing Chatterbox import..." -ForegroundColor Cyan
& $venvPython -c "from chatterbox.tts import ChatterboxTTS; print('Chatterbox import OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Chatterbox installed but could not be imported."
}

Write-Host ""
Write-Host "Natural voice upgrade is installed." -ForegroundColor Green
Write-Host "The first Story render will download the Chatterbox model into:" -ForegroundColor Yellow
Write-Host "  $hfCache" -ForegroundColor Yellow
Write-Host "Restart Shorts Studio after this installer finishes."
Write-Host ""
