@echo off
echo ============================================
echo  Derby Dash — Windows Executable Builder
echo ============================================
echo.

:: Install dependencies
echo [1/3] Installing Python dependencies...
py -3 -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Make sure Python is in your PATH.
    pause
    exit /b 1
)

:: Build the executable
echo.
echo [2/3] Building executable with PyInstaller...
py -3 -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "Derby Dash" ^
    --add-data "constants.py;." ^
    --add-data "game_state.py;." ^
    --add-data "board_widget.py;." ^
    --add-data "control_panel.py;." ^
    --add-data "admin_dialog.py;." ^
    --add-data "webcam_dialog.py;." ^
    --add-data "main_window.py;." ^
    --add-data "styles.py;." ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtGui ^
    --hidden-import PyQt6.QtWidgets ^
    --collect-all PyQt6 ^
    main.py

if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Done!
echo.
echo  Executable: dist\Derby Dash.exe
echo.
echo  NOTE: The executable includes the webcam dice reader.
echo  If OpenCV is not available it will still run with manual dice entry.
echo.
pause
