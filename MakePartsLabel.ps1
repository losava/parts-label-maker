# ============================================================
#  Parts Label Generator (PowerShell)
#  Creates 3" x 2" PDF parts labels with Code 128 barcode
#  Loops so you can make multiple labels in one session
# ============================================================

$Host.UI.RawUI.WindowTitle = "Parts Label Generator"

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Green
Write-Host "       PARTS LABEL GENERATOR" -ForegroundColor Green
Write-Host "  ========================================" -ForegroundColor Green
Write-Host ""

# Check Python
try {
    $null = python --version 2>&1
} catch {
    Write-Host "  [ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Please install Python from https://www.python.org"
    Write-Host "  and make sure 'Add Python to PATH' is checked."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check / install packages
Write-Host "  Checking required packages..." -ForegroundColor Cyan
python -c "import barcode, reportlab, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing required packages (one-time)..." -ForegroundColor Yellow
    pip install python-barcode pillow reportlab --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to install packages." -ForegroundColor Red
        Write-Host "  Try running:  pip install python-barcode pillow reportlab"
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "  Packages installed successfully." -ForegroundColor Green
    Write-Host ""
}

# Locate the Python script (same folder as this .ps1)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $scriptDir "make_parts_label.py"

if (-not (Test-Path $pyScript)) {
    Write-Host "  [ERROR] make_parts_label.py not found in:" -ForegroundColor Red
    Write-Host "          $scriptDir"
    Write-Host ""
    Write-Host "  Make sure both files are in the same folder."
    Read-Host "Press Enter to exit"
    exit 1
}

# Run interactive continuous mode
python $pyScript

Write-Host ""
Read-Host "Press Enter to exit"
