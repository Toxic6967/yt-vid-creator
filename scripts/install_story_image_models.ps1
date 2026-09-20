$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Shorts Studio - High Quality Story Images ===" -ForegroundColor Cyan
Write-Host "Installs FLUX.2 Klein 4B FP8 reference editing for Roblox Story keyframes."
Write-Host ""

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
        Name = "FLUX.2 Klein 4B FP8"
        Dir = Join-Path $models "diffusion_models"
        File = "flux-2-klein-4b-fp8.safetensors"
        Url = "https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors?download=true"
        ExpectedBytes = 3790000000
    },
    @{
        Name = "FLUX.2 Klein Qwen 3 4B FP4 text encoder"
        Dir = Join-Path $models "text_encoders"
        File = "qwen_3_4b_fp4_flux2.safetensors"
        Url = "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/resolve/main/split_files/text_encoders/qwen_3_4b_fp4_flux2.safetensors?download=true"
        ExpectedBytes = 3850000000
    },
    @{
        Name = "FLUX.2 VAE"
        Dir = Join-Path $models "vae"
        File = "flux2-vae.safetensors"
        Url = "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/resolve/main/split_files/vae/flux2-vae.safetensors?download=true"
        ExpectedBytes = 336211292
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

    Write-Host ""
    Write-Host "Preparing $($item.Name)..." -ForegroundColor Yellow

    $partial = "$dest.part"
    $partialBytes = 0
    if (Test-Path $partial) {
        $partialBytes = (Get-Item $partial).Length
        $partialGB = [math]::Round($partialBytes / 1GB, 2)
        Write-Host "Found partial download ($partialGB GB). It will resume." -ForegroundColor Yellow
    }

    $driveRoot = [IO.Path]::GetPathRoot($dest)
    $drive = New-Object System.IO.DriveInfo($driveRoot)
    $remaining = [math]::Max(0, [int64]$item.ExpectedBytes - [int64]$partialBytes)
    $safety = 1GB
    if ($drive.AvailableFreeSpace -lt ($remaining + $safety)) {
        $freeGB = [math]::Round($drive.AvailableFreeSpace / 1GB, 2)
        $needGB = [math]::Round(($remaining + $safety) / 1GB, 2)
        throw "Not enough free space on $driveRoot. Free: $freeGB GB. Need about $needGB GB including safety space."
    }

    Write-Host "Downloading/resuming $($item.Name)..." -ForegroundColor Yellow
    Write-Host "Do not close this window. If it is interrupted, rerun this installer and it will resume."
    & curl.exe -L --fail --retry 5 --retry-delay 5 --continue-at - --progress-bar -o $partial $item.Url

    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $partial) {
            $savedGB = [math]::Round((Get-Item $partial).Length / 1GB, 2)
            Write-Host "Partial download kept: $savedGB GB" -ForegroundColor Yellow
        }
        throw "Download paused/failed for $($item.Name). The partial file was kept so the next run can resume."
    }

    if ((Get-Item $partial).Length -lt 1000000) {
        throw "Downloaded file for $($item.Name) is unexpectedly small."
    }

    Move-Item -LiteralPath $partial -Destination $dest -Force
    $gb = [math]::Round((Get-Item $dest).Length / 1GB, 2)
    Write-Host "[OK] Installed $($item.File) ($gb GB)." -ForegroundColor Green
}

Write-Host ""
Write-Host "High-quality Story image models installed." -ForegroundColor Green
Write-Host "Completely close ComfyUI, reopen it, then restart Shorts Studio."
Write-Host ""
