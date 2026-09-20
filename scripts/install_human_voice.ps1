$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Shorts Studio - Human Voice Setup ===" -ForegroundColor Cyan
Write-Host "Installs Kokoro ONNX and the local voice model used by Story Studio."
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
    throw "Shorts Studio storage root is empty. Run setup_external_storage.bat first."
}
if (-not (Test-Path ([IO.Path]::GetPathRoot($storageRoot)))) {
    throw "Storage drive is unavailable: $storageRoot"
}

$modelDir = Join-Path $storageRoot "data\assets\kokoro"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
Write-Host "Voice model folder: $modelDir" -ForegroundColor Green

Write-Host "Installing Python voice packages..." -ForegroundColor Yellow
& py -m pip install --upgrade "kokoro-onnx>=0.6.1,<0.7" "soundfile>=0.13,<1"
if ($LASTEXITCODE -ne 0) {
    throw "Python package installation failed."
}

$targets = @(
    @{
        Name = "Kokoro v1.0 voice model"
        File = "kokoro-v1.0.onnx"
        Url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
    },
    @{
        Name = "Kokoro v1.0 voices"
        File = "voices-v1.0.bin"
        Url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"
    }
)

foreach ($item in $targets) {
    $dest = Join-Path $modelDir $item.File
    if (Test-Path $dest) {
        $mb = [math]::Round((Get-Item $dest).Length / 1MB, 1)
        Write-Host "[OK] $($item.File) already exists ($mb MB)." -ForegroundColor Green
        continue
    }

    Write-Host ""
    Write-Host "Downloading $($item.Name)..." -ForegroundColor Yellow
    & curl.exe -L --fail --retry 3 --retry-delay 5 --progress-bar -o $dest $item.Url
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $dest) { Remove-Item $dest -Force }
        throw "Download failed for $($item.Name)."
    }
    if ((Get-Item $dest).Length -lt 1000000) {
        Remove-Item $dest -Force
        throw "Downloaded $($item.File) is unexpectedly small."
    }

    $mb = [math]::Round((Get-Item $dest).Length / 1MB, 1)
    Write-Host "[OK] Installed $($item.File) ($mb MB)." -ForegroundColor Green
}

Write-Host ""
Write-Host "Testing Kokoro import..." -ForegroundColor Cyan
& py -c "from kokoro_onnx import Kokoro; print('Kokoro import OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro installed, but Python could not import it."
}

Write-Host ""
Write-Host "Human Story voice is ready." -ForegroundColor Green
Write-Host "Restart Shorts Studio after this installer finishes."
Write-Host ""
