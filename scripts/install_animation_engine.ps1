$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "=== Shorts Studio V3 - Roblox Animation Engine ===" -ForegroundColor Cyan
Write-Host "This installs/checks Blender for deterministic R15 animation."
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
if (Test-Path $storageMarker) {
    $storageRoot = (Get-Content $storageMarker -Raw).Trim()
}
else {
    $storageRoot = "E:\auto yt"
}
if (-not $storageRoot) {
    throw "Storage root is empty. Run setup_external_storage.bat first."
}

$robloxAssetDir = Join-Path $storageRoot "data\assets\roblox_official"
$robloxR15 = Join-Path $robloxAssetDir "BlockyCharacter.fbx"
New-Item -ItemType Directory -Force -Path $robloxAssetDir | Out-Null

if (-not (Test-Path $robloxR15)) {
    Write-Host ""
    Write-Host "Downloading Roblox's official Blocky R15 reference character..." -ForegroundColor Yellow
    $url = "https://prod.docsiteassets.roblox.com/assets/avatar/dynamic-heads/reference-files/BlockyCharacter.fbx"
    try {
        Invoke-WebRequest -Uri $url -OutFile $robloxR15 -UseBasicParsing
    }
    catch {
        if (Test-Path $robloxR15) { Remove-Item $robloxR15 -Force -ErrorAction SilentlyContinue }
        throw "Could not download the official Roblox BlockyCharacter.fbx reference: $($_.Exception.Message)"
    }
}

if ((Get-Item $robloxR15).Length -lt 100000) {
    throw "The downloaded Roblox R15 reference looks incomplete: $robloxR15"
}

Write-Host "Official Roblox R15 reference:" -ForegroundColor Green
Write-Host "  $robloxR15" -ForegroundColor Green

Write-Host ""
Write-Host "Testing that Blender can import the official Roblox R15 FBX..." -ForegroundColor Yellow
$escapedR15 = $robloxR15.Replace("\", "\\")
& $blender --background --factory-startup --python-expr "import bpy; bpy.ops.import_scene.fbx(filepath=r'$escapedR15'); print('Official Roblox R15 import OK', len(bpy.context.scene.objects))"
if ($LASTEXITCODE -ne 0) {
    throw "Blender is installed, but importing the official Roblox R15 reference failed."
}

Write-Host ""
Write-Host "V3 Roblox animation engine is ready." -ForegroundColor Green
Write-Host "Restart Shorts Studio after this installer finishes."
Write-Host ""
