@echo off
setlocal
cd /d "%~dp0"

rem Build a distributable release folder for HandBrakePlus.

call "%~dp0build_exe.bat"
if errorlevel 1 goto :error

set "RELEASE_DIR=%~dp0release\HandBrakePlus"

echo Preparing release directory...
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

copy /y "%~dp0dist\HandBrakePlus.exe" "%RELEASE_DIR%\HandBrakePlus.exe" >nul
copy /y "%~dp0README.md" "%RELEASE_DIR%\README.md" >nul
copy /y "%~dp0config.example.json" "%RELEASE_DIR%\config.example.json" >nul

echo.
echo Release folder ready: %RELEASE_DIR%
goto :end

:error
echo.
echo Release build failed.
pause
exit /b 1

:end
endlocal