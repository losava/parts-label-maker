# Build PartsLabel.exe and the per-user Inno Setup installer.
# Requires Python, the packages in requirements-dev.txt, and Inno Setup 6.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$version = python -c "import version; print(version.__version__)"
Write-Host "Building Parts Label $version"

python -m PyInstaller --noconfirm --clean --windowed --name PartsLabel `
    --icon packaging\parts-label.ico `
    --collect-all barcode `
    --collect-all reportlab `
    --collect-all PIL `
    --hidden-import win32print `
    --hidden-import win32api `
    parts_label_app.py

$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 (ISCC.exe) was not found. Install it from https://jrsoftware.org/isdl.php"
}

& $iscc "/DMyAppVersion=$version" "packaging\windows\parts_label.iss"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installer: dist\PartsLabel-Setup-$version.exe"
