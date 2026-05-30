@echo off
setlocal
cd /d "%~dp0"

rem Build a standalone HandBrakePlus Windows executable with PyInstaller.

set "PYTHON_EXE="
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python.exe"

echo Using Python: %PYTHON_EXE%
"%PYTHON_EXE%" -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    "%PYTHON_EXE%" -m pip install pyinstaller
    if errorlevel 1 goto :error
)

echo Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building HandBrakePlus.exe...
"%PYTHON_EXE%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name HandBrakePlus ^
    --icon "assets\handbrakeplus.ico" ^
    --add-data "app;app" ^
    --add-data "assets;assets" ^
    main.py
if errorlevel 1 goto :error

echo.
echo Build succeeded.
echo EXE: %~dp0dist\HandBrakePlus.exe
goto :end

:error
echo.
echo Build failed.
pause
exit /b 1

:end
endlocal