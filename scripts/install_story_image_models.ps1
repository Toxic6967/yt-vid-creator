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
    },
    @{
        Name = "Qwen 3 4B image text encoder"
        Dir = Join-Path $models "text_encoders"
        File = "qwen_3_4b.safetensors"
        Url = "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors?download=true"
    },
    @{
        Name = "FLUX.2 VAE"
        Dir = Join-Path $models "vae"
        File = "flux2-vae.safetensors"
        Url = "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors?download=true"
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
    Write-Host "Downloading $($item.Name)..." -ForegroundColor Yellow
    Write-Host "Large download - do not close this window."
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
Write-Host "High-quality Story image models installed." -ForegroundColor Green
Write-Host "Completely close ComfyUI, reopen it, then restart Shorts Studio."
Write-Host ""
