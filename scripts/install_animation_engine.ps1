$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "=== Shorts Studio V5 - Roblox Machinima Engine ===" -ForegroundColor Cyan
Write-Host "This installs/checks Blender for deterministic Roblox-style 3D animation."
Write-Host ""

function Find-Blender {
    $candidates = @()

    $cmd = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }

    $pf = $env:ProgramFiles
    if ($pf) {
        $root = Join-Path $pf "Blender Foundation"
        if (Test-Path $root) {
            $candidates += Get-ChildItem $root -Filter blender.exe -Recurse -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
        }
    }

    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    return $null
}

$blender = Find-Blender
if (-not $blender) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Blender was not found and winget is unavailable. Install Blender from blender.org, then rerun this installer."
    }

    Write-Host "Blender was not found. Installing it with winget..." -ForegroundColor Yellow
    & winget install --id BlenderFoundation.Blender --exact --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install Blender. Install Blender manually, then rerun this installer."
    }

    Start-Sleep -Seconds 2
    $blender = Find-Blender
}

if (-not $blender) {
    throw "Blender installation finished, but blender.exe could not be located. Restart Windows or install Blender manually."
}

Write-Host "Blender found:" -ForegroundColor Green
Write-Host "  $blender" -ForegroundColor Green

Write-Host ""
Write-Host "Testing headless Blender..." -ForegroundColor Yellow
& $blender --background --factory-startup --python-expr "import bpy; print('Shorts Studio Blender OK', bpy.app.version_string)"
if ($LASTEXITCODE -ne 0) {
    throw "Blender is installed but the headless test failed."
}

$storageMarker = Join-Path $projectRoot ".shorts_studio_storage"
$storageRoot = $null
if (Test-Path $storageMarker) {
    $storageRoot = (Get-Content $storageMarker -Raw).Trim()
}

# V5 no longer depends on Roblox's FBX importing correctly. It builds the
# segmented Roblox-style character rig directly in Blender. Keep the official
# reference as an OPTIONAL legacy asset when storage is configured, but never
# fail installation just because Roblox changes or removes the download.
if ($storageRoot) {
    $robloxAssetDir = Join-Path $storageRoot "data\assets\roblox_official"
    $robloxR15 = Join-Path $robloxAssetDir "BlockyCharacter.fbx"
    New-Item -ItemType Directory -Force -Path $robloxAssetDir | Out-Null

    if (-not (Test-Path $robloxR15)) {
        Write-Host ""
        Write-Host "Optional: trying to download Roblox's legacy Blocky R15 reference..." -ForegroundColor DarkYellow
        $url = "https://prod.docsiteassets.roblox.com/assets/avatar/dynamic-heads/reference-files/BlockyCharacter.fbx"
        try {
            Invoke-WebRequest -Uri $url -OutFile $robloxR15 -UseBasicParsing
            if ((Get-Item $robloxR15).Length -lt 100000) {
                Remove-Item $robloxR15 -Force -ErrorAction SilentlyContinue
                Write-Host "Legacy R15 reference download was incomplete; V5 will continue without it." -ForegroundColor DarkYellow
            }
            else {
                Write-Host "Optional legacy R15 reference saved: $robloxR15" -ForegroundColor DarkGreen
            }
        }
        catch {
            if (Test-Path $robloxR15) { Remove-Item $robloxR15 -Force -ErrorAction SilentlyContinue }
            Write-Host "Legacy R15 reference was unavailable; this does NOT block V5 rendering." -ForegroundColor DarkYellow
        }
    }
}

Write-Host ""
Write-Host "V5 Roblox machinima engine is ready." -ForegroundColor Green
Write-Host "Restart Shorts Studio after this installer finishes."
Write-Host ""
