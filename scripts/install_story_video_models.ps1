$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Shorts Studio - Cinematic Story Video Setup ===" -ForegroundColor Cyan
Write-Host "Installs the lightweight LTX 2B FP8 image-to-video backend."
Write-Host "This is used to animate our generated Roblox movie keyframes."
Write-Host ""

$installations = Join-Path $env:APPDATA "Comfy Desktop\installations.json"
if (-not (Test-Path $installations)) {
    throw "Could not find Comfy Desktop installations.json: $installations"
}

$items = Get-Content $installations -Raw | ConvertFrom-Json
$install = $items |
    Where-Object { $_.sourceId -eq "standalone" -and $_.status -eq "installed" } |
    Select-Object -First 1

if (-not $install) {
    throw "Could not find an installed local ComfyUI instance."
}

$installRoot = [IO.Path]::GetFullPath([string]$install.installPath)
$folderPaths = Get-ChildItem -Path $installRoot -Filter "folder_paths.py" -File -Recurse -ErrorAction SilentlyContinue |
    Sort-Object { $_.FullName.Length } |
    Select-Object -First 1

if ($folderPaths) {
    $comfyRoot = $folderPaths.Directory.FullName
}
elseif (Test-Path (Join-Path $installRoot "ComfyUI\models")) {
    $comfyRoot = Join-Path $installRoot "ComfyUI"
}
else {
    $comfyRoot = $installRoot
}

$models = Join-Path $comfyRoot "models"
Write-Host "Actual ComfyUI root: $comfyRoot" -ForegroundColor Green
Write-Host "Model root:          $models" -ForegroundColor Green
Write-Host ""

$targets = @(
    @{
        Name = "LTX 2B distilled FP8 story video model"
        Dir = Join-Path $models "checkpoints"
        File = "ltxv-2b-0.9.8-distilled-fp8.safetensors"
        Url = "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled-fp8.safetensors?download=true"
    },
    @{
        Name = "LTX T5 XXL FP8 text encoder"
        Dir = Join-Path $models "text_encoders"
        File = "t5xxl_fp8_e4m3fn_scaled.safetensors"
        Url = "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors?download=true"
    }
)

foreach ($item in $targets) {
    New-Item -ItemType Directory -Force -Path $item.Dir | Out-Null
    $dest = Join-Path $item.Dir $item.File

    if (Test-Path $dest) {
        $gb = [math]::Round((Get-Item $dest).Length / 1GB, 2)
        Write-Host "[OK] $($item.File) already installed ($gb GB)." -ForegroundColor Green
        continue
    }

    Write-Host "Downloading $($item.Name)..." -ForegroundColor Yellow
    Write-Host "This is a large download. Do not close the window."
    & curl.exe -L --fail --retry 3 --retry-delay 5 --progress-bar -o $dest $item.Url

    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $dest) { Remove-Item $dest -Force }
        throw "Download failed for $($item.Name)."
    }

    if ((Get-Item $dest).Length -lt 1000000) {
        Remove-Item $dest -Force
        throw "Downloaded file for $($item.Name) is unexpectedly small."
    }

    $gb = [math]::Round((Get-Item $dest).Length / 1GB, 2)
    Write-Host "[OK] Installed $($item.File) ($gb GB)." -ForegroundColor Green
}

Write-Host ""
Write-Host "Cinematic story video models installed." -ForegroundColor Green
Write-Host "Completely close ComfyUI, reopen it, then restart Shorts Studio."
Write-Host "Story mode will prefer keyframe-to-video when this backend is detected."
Write-Host ""
