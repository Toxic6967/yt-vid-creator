$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Shorts Studio - Wan 2.1 Video Setup ===" -ForegroundColor Cyan

$installations = Join-Path $env:APPDATA "Comfy Desktop\installations.json"
if (-not (Test-Path $installations)) {
    throw "Could not find Comfy Desktop installations.json at: $installations"
}

$items = Get-Content $installations -Raw | ConvertFrom-Json
$install = $items |
    Where-Object { $_.sourceId -eq "standalone" -and $_.status -eq "installed" } |
    Select-Object -First 1

if (-not $install) {
    throw "Could not find an installed local ComfyUI instance."
}

$installRoot = [IO.Path]::GetFullPath([string]$install.installPath)
if (-not (Test-Path $installRoot)) {
    throw "ComfyUI install path does not exist: $installRoot"
}

# New Comfy Desktop installations may use <installPath>\ComfyUI as the actual
# backend directory. Locate the folder containing ComfyUI's folder_paths.py
# instead of guessing.
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

$models = Join-Path $storageRoot "models"
New-Item -ItemType Directory -Force -Path $models | Out-Null

Write-Host "Installation record: $installRoot"
Write-Host "Actual ComfyUI root: $comfyRoot" -ForegroundColor Green
Write-Host "External model root: $models" -ForegroundColor Green
Write-Host ""

function Move-ExistingModel {
    param(
        [string]$FileName,
        [string]$Destination
    )

    if (Test-Path $Destination) {
        return $true
    }

    $found = Get-ChildItem -Path $installRoot -Filter $FileName -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -ne $Destination } |
        Select-Object -First 1

    if ($found) {
        Write-Host "Found existing download:" -ForegroundColor Yellow
        Write-Host "  $($found.FullName)"
        Write-Host "Moving it to the external Shorts Studio model folder..."
        New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
        Move-Item -LiteralPath $found.FullName -Destination $Destination -Force
        return $true
    }

    return $false
}

# Also repair an SDXL checkpoint if it was placed beside the wrong models root.
$sdxlName = "sd_xl_base_1.0.safetensors"
$sdxlDest = Join-Path (Join-Path $models "checkpoints") $sdxlName
if (-not (Test-Path $sdxlDest)) {
    [void](Move-ExistingModel -FileName $sdxlName -Destination $sdxlDest)
}

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
        Write-Host "[OK] $($item.Name) is already in the correct folder." -ForegroundColor Green
        continue
    }

    if (Move-ExistingModel -FileName $item.File -Destination $dest) {
        Write-Host "[OK] Moved $($item.File) into the correct folder." -ForegroundColor Green
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
Write-Host "Verifying files in the external Shorts Studio model root..." -ForegroundColor Cyan
$allGood = $true
foreach ($item in $targets) {
    $dest = Join-Path $item.Dir $item.File
    if (Test-Path $dest) {
        $sizeGB = [math]::Round((Get-Item $dest).Length / 1GB, 2)
        Write-Host "[OK] $($item.File) ($sizeGB GB)" -ForegroundColor Green
    }
    else {
        Write-Host "[MISSING] $dest" -ForegroundColor Red
        $allGood = $false
    }
}

if (-not $allGood) {
    throw "One or more Wan model files are still missing."
}

Write-Host ""
Write-Host "Wan 2.1 video models are in the external model root." -ForegroundColor Green
Write-Host "IMPORTANT: Completely close ComfyUI, reopen it, then restart Shorts Studio."
Write-Host ""
