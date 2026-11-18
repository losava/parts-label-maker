@echo off
setlocal
title Parts Label
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python was not found.
    echo  Install from https://www.python.org/downloads/
    echo  Check "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

python -c "import barcode, reportlab, PIL" >nul 2>&1
if errorlevel 1 (
    echo  Installing packages - please wait...
    python -m pip install python-barcode pillow reportlab --quiet
)

python -c "import win32print" >nul 2>&1
if errorlevel 1 (
    echo  Installing print support...
    python -m pip install pywin32 --quiet
)

if not exist "parts_label_app.py" (
    echo  [ERROR] parts_label_app.py is missing from this folder.
    pause
    exit /b 1
)

REM Windowed app — no console. Falls back to python if pythonw is missing.
where pythonw >nul 2>&1
if errorlevel 1 (
    start "" python parts_label_app.py
) else (
    start "" pythonw parts_label_app.py
)
exit /b 0
