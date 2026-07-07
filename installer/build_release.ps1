$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$stageRoot = Join-Path $projectRoot 'build_stage'
$stageApp = Join-Path $stageRoot 'backup_manager_main.py'
$stageAssets = Join-Path $stageRoot 'assets'
$distDir = Join-Path $stageRoot 'dist_onedir'
$workDir = Join-Path $stageRoot 'build_onedir'
$innoScript = Join-Path $PSScriptRoot 'BackupManager.iss'

$isccCandidates = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw 'ISCC.exe não encontrado. Instale o Inno Setup 6.'
}

New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stageAssets | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot 'copy.py') -Destination $stageApp -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'rclone.exe') -Destination (Join-Path $stageRoot 'rclone.exe') -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'assets\app_icon.ico') -Destination (Join-Path $stageAssets 'app_icon.ico') -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'assets\app_icon.png') -Destination (Join-Path $stageAssets 'app_icon.png') -Force

if (Test-Path -LiteralPath $distDir) {
    Remove-Item -LiteralPath $distDir -Recurse -Force
}
if (Test-Path -LiteralPath $workDir) {
    Remove-Item -LiteralPath $workDir -Recurse -Force
}

Push-Location $stageRoot
try {
    pyinstaller --noconfirm --clean `
        --distpath $distDir `
        --workpath $workDir `
        --windowed `
        --name "Backup Manager" `
        --icon "assets\app_icon.ico" `
        --add-binary "rclone.exe;." `
        --add-data "assets\app_icon.png;assets" `
        --add-data "assets\app_icon.ico;assets" `
        "backup_manager_main.py"
}
finally {
    Pop-Location
}

& $iscc $innoScript
