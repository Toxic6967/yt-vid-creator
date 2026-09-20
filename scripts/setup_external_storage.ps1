param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$storageRoot = "E:\auto yt"
$marker = Join-Path $projectRoot ".shorts_studio_storage"

function Say([string]$Text, [ConsoleColor]$Color = [ConsoleColor]::Gray) {
    if (-not $Quiet) {
        Write-Host $Text -ForegroundColor $Color
    }
}

Say ""
Say "=== Shorts Studio - Move Heavy Storage to E: ===" Cyan
Say "Destination: $storageRoot" Green
Say ""

if (-not (Test-Path "E:\")) {
    throw "E: drive is not available. Connect/mount E: and run this again."
}

try {
    $ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8765, 8188 }
    if ($ports) {
        $used = ($ports | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object) -join ", "
        throw "Close Shorts Studio and ComfyUI first. Listening port(s): $used"
    }
}
catch {
    if ($_.Exception.Message -like "Close Shorts Studio*") { throw }
}

$dirs = @(
    $storageRoot,
    (Join-Path $storageRoot "models"),
    (Join-Path $storageRoot "models\checkpoints"),
    (Join-Path $storageRoot "models\diffusion_models"),
    (Join-Path $storageRoot "models\text_encoders"),
    (Join-Path $storageRoot "models\vae"),
    (Join-Path $storageRoot "data"),
    (Join-Path $storageRoot "data\outputs"),
    (Join-Path $storageRoot "data\assets"),
    (Join-Path $storageRoot "data\assets\kokoro"),
    (Join-Path $storageRoot "data\cache")
)
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

function Move-OneFile {
    param(
        [string]$Source,
        [string]$Destination
    )
    if (-not (Test-Path $Source)) { return }

    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null

    if (Test-Path $Destination) {
        $sourceSize = (Get-Item $Source).Length
        $destSize = (Get-Item $Destination).Length
        if ($sourceSize -eq $destSize) {
            Remove-Item -LiteralPath $Source -Force
            Say "[OK] Existing external copy verified; removed duplicate from C: $(Split-Path $Source -Leaf)" Green
            return
        }

        $dupe = "$Destination.from-c-drive"
        Move-Item -LiteralPath $Source -Destination $dupe -Force
        Say "[WARN] Destination differed; preserved C: copy as $(Split-Path $dupe -Leaf)" Yellow
        return
    }

    Move-Item -LiteralPath $Source -Destination $Destination -Force
    Say "[MOVED] $(Split-Path $Source -Leaf) -> $Destination" Green
}

function Move-DirectoryContents {
    param(
        [string]$SourceDir,
        [string]$DestinationDir
    )
    if (-not (Test-Path $SourceDir)) { return }
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null

    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        $dest = Join-Path $DestinationDir $_.Name
        if ($_.PSIsContainer) {
            Move-DirectoryContents -SourceDir $_.FullName -DestinationDir $dest
            if ((Get-ChildItem -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
        }
        else {
            Move-OneFile -Source $_.FullName -Destination $dest
        }
    }
}

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
$oldModels = Join-Path $comfyRoot "models"
$newModels = Join-Path $storageRoot "models"

Say "ComfyUI backend: $comfyRoot"
Say "External models: $newModels" Green
Say ""

$modelMap = @(
    @("checkpoints", "sd_xl_base_1.0.safetensors"),
    @("checkpoints", "ltxv-2b-0.9.8-distilled-fp8.safetensors"),
    @("diffusion_models", "wan2.1_t2v_1.3B_fp16.safetensors"),
    @("diffusion_models", "flux-2-klein-4b-fp8.safetensors"),
    @("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    @("text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors"),
    @("text_encoders", "qwen_3_4b.safetensors"),
    @("text_encoders", "qwen_3_4b_fp4_flux2.safetensors"),
    @("vae", "wan_2.1_vae.safetensors"),
    @("vae", "flux2-vae.safetensors")
)

foreach ($entry in $modelMap) {
    $folder = $entry[0]
    $file = $entry[1]
    Move-OneFile -Source (Join-Path (Join-Path $oldModels $folder) $file) -Destination (Join-Path (Join-Path $newModels $folder) $file)
    Move-OneFile -Source (Join-Path (Join-Path $oldModels $folder) "$file.part") -Destination (Join-Path (Join-Path $newModels $folder) "$file.part")
}

$yamlPath = Join-Path $comfyRoot "extra_model_paths.yaml"
$begin = "# BEGIN SHORTS_STUDIO_EXTERNAL"
$end = "# END SHORTS_STUDIO_EXTERNAL"
$managed = @"
$begin
shorts_studio_external:
  base_path: 'E:/auto yt/models'
  is_default: true
  checkpoints: checkpoints
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  vae: vae
$end
"@

$existing = ""
if (Test-Path $yamlPath) {
    $existing = Get-Content $yamlPath -Raw
    $pattern = "(?s)\r?\n?# BEGIN SHORTS_STUDIO_EXTERNAL.*?# END SHORTS_STUDIO_EXTERNAL\r?\n?"
    $existing = [regex]::Replace($existing, $pattern, "")
}
$newYaml = ($existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $managed.Trim() + [Environment]::NewLine).TrimStart()
Set-Content -LiteralPath $yamlPath -Value $newYaml -Encoding UTF8
Say "[OK] ComfyUI external model path registered." Green

$oldData = Join-Path $projectRoot "data"
$newData = Join-Path $storageRoot "data"
if (Test-Path $oldData) {
    Move-DirectoryContents -SourceDir $oldData -DestinationDir $newData
}
Say "[OK] Shorts Studio data now lives at $newData" Green

Set-Content -LiteralPath $marker -Value $storageRoot -Encoding UTF8
Say "[OK] Storage marker written: $marker" Green

Say ""
Say "External storage setup complete." Green
Say "Heavy Shorts Studio files now go under: $storageRoot" Green
Say ""
Say "IMPORTANT: restart ComfyUI so it loads extra_model_paths.yaml." Yellow
Say "Then restart Shorts Studio with: py run.py" Yellow
Say ""
