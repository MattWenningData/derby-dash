@echo off
setlocal EnableDelayedExpansion
title Truck Dash — Build ^& Installer

echo.
echo  =====================================================
echo   Truck Dash  ^|  Build ^& Installer Script
echo  =====================================================
echo.

:: ── Step 1: Python check ─────────────────────────────────────────────────────
echo [1/5] Checking Python...
py -3 --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: Python not found.
    echo  Please install Python 3.11+ from https://python.org
    echo  Make sure to check "Add Python to PATH" during install.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('py -3 --version 2^>^&1') do echo   Found: %%v

:: ── Step 2: Install Python dependencies ─────────────────────────────────────
echo.
echo [2/5] Installing Python dependencies...
py -3 -m pip install -q --upgrade pip
py -3 -m pip install -q PyQt6 opencv-python numpy pyinstaller
if %ERRORLEVEL% neq 0 (
    echo  ERROR: pip install failed.
    pause & exit /b 1
)
echo   Dependencies OK.

:: ── Step 3: Generate icon ────────────────────────────────────────────────────
echo.
echo [3/5] Generating app icon...
py -3 make_icon.py
if not exist TruckDash.ico (
    echo   WARNING: Icon generation failed — installer will use default icon.
)

:: ── Step 4: Build executable with PyInstaller ────────────────────────────────
echo.
echo [4/5] Building executable with PyInstaller...
echo   (This may take 2-5 minutes — please wait)
echo.

if exist dist\TruckDash rd /s /q dist\TruckDash
if exist build rd /s /q build

py -3 -m PyInstaller TruckDash.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: PyInstaller build failed. See output above.
    pause & exit /b 1
)

if not exist "dist\TruckDash\TruckDash.exe" (
    echo  ERROR: TruckDash.exe not found after build.
    pause & exit /b 1
)
echo.
echo   Executable built successfully: dist\TruckDash\TruckDash.exe

:: ── Step 5: Build installer with Inno Setup ──────────────────────────────────
echo.
echo [5/5] Building installer...

:: Look for Inno Setup in common locations
set ISCC=
for %%p in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
) do (
    if exist %%p set ISCC=%%p
)

if "%ISCC%"=="" (
    echo   Inno Setup not found — attempting to install via winget...
    winget install JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    :: Re-check after install
    for %%p in (
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) do (
        if exist %%p set ISCC=%%p
    )
)

if "%ISCC%"=="" (
    echo.
    echo  ----------------------------------------------------------------
    echo   Inno Setup not found and could not be installed automatically.
    echo.
    echo   TO CREATE THE INSTALLER MANUALLY:
    echo    1. Download Inno Setup (free) from:
    echo       https://jrsoftware.org/isdl.php
    echo    2. Install it, then run:
    echo       "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
    echo.
    echo   The app itself is ready at:  dist\TruckDash\TruckDash.exe
    echo  ----------------------------------------------------------------
    echo.
    pause & exit /b 0
)

if not exist installer_output mkdir installer_output
%ISCC% installer.iss
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Inno Setup build failed.
    pause & exit /b 1
)

echo.
echo  =====================================================
echo   BUILD COMPLETE!
echo.
echo   Installer:   installer_output\TruckDash_Setup.exe
echo   Portable:    dist\TruckDash\TruckDash.exe
echo  =====================================================
echo.
echo  Share TruckDash_Setup.exe with anyone — they just
echo  double-click it to install, no Python required!
echo.
pause
