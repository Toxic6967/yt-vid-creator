$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Shorts Studio - Wan 2.1 Video Setup ===" -ForegroundColor Cyan

$installations = Join-Path $env:APPDATA "Comfy Desktop\installations.json"
if (-not (Test-Path $installations)) {
    throw "Could not find Comfy Desktop installations.json at: $installations"
}

$items = Get-Content $installations -Raw | ConvertFrom-Json
$install = $items | Where-Object { $_.sourceId -eq "standalone" -and $_.status -eq "installed" } | Select-Object -First 1
if (-not $install) {
    throw "Could not find an installed local ComfyUI instance."
}

$comfy = $install.installPath
$models = Join-Path $comfy "models"

# If the user already has SDXL somewhere under this install, use its models root.
$sdxl = Get-ChildItem -Path $comfy -Filter "sd_xl_base_1.0.safetensors" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($sdxl -and $sdxl.Directory.Name -eq "checkpoints") {
    $models = Split-Path $sdxl.Directory.FullName -Parent
}

Write-Host "ComfyUI: $comfy"
Write-Host "Models:  $models"
Write-Host ""

$targets = @(
    @{
        Name = "Wan 2.1 T2V 1.3B"
        Dir = Join-Path $models "diffusion_models"
        File = "wan2.1_t2v_1.3B_fp16.safetensors"
        Url = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors?download=true"
    },
    @{
        Name = "Wan UMT5 text encoder"
        Dir = Join-Path $models "text_encoders"
        File = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
        Url = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors?download=true"
    },
    @{
        Name = "Wan 2.1 VAE"
        Dir = Join-Path $models "vae"
        File = "wan_2.1_vae.safetensors"
        Url = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors?download=true"
    }
)

foreach ($item in $targets) {
    New-Item -ItemType Directory -Force -Path $item.Dir | Out-Null
    $dest = Join-Path $item.Dir $item.File

    if (Test-Path $dest) {
        Write-Host "[OK] $($item.Name) already exists." -ForegroundColor Green
        continue
    }

    Write-Host ""
    Write-Host "Downloading $($item.Name)..." -ForegroundColor Yellow
    Write-Host "This is a large model download. Do not close this window."

    & curl.exe -L --fail --retry 3 --retry-delay 5 --progress-bar -o $dest $item.Url
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $dest) { Remove-Item $dest -Force }
        throw "Download failed for $($item.Name)."
    }

    if ((Get-Item $dest).Length -lt 1000000) {
        Remove-Item $dest -Force
        throw "Downloaded file for $($item.Name) is unexpectedly small."
    }

    Write-Host "[OK] Installed $($item.File)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Wan 2.1 video models are installed." -ForegroundColor Green
Write-Host "Close ComfyUI completely and reopen it, then restart Shorts Studio."
Write-Host ""
