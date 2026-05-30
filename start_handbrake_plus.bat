@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python.exe"

"%PYTHON_EXE%" "%~dp0main.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo HandBrakePlus exited with code %EXIT_CODE%.
    echo Check that Python is installed and HandBrakeCLI path is configured correctly.
    pause
)

endlocal
