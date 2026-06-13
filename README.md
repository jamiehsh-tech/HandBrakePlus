# HandBrakePlus

A small Windows desktop batch encoder for HandBrakeCLI.

HandBrakePlus 是一个基于 HandBrakeCLI 的二次开发工具，面向批量编码场景，提供更方便的批量导入、片段拆分、任务展开和顺序编码体验。

HandBrakePlus is a secondary-development wrapper built on top of HandBrakeCLI for batch encoding workflows. It makes bulk import, clip range splitting, job expansion, and sequential encoding easier to manage.

安装必要文件:
Set-Location "path\to\HandBrakePlus"
python.exe -m pip install -r requirements.txt

启动程序,终端执行: python.exe main.py

打包 exe:
.\build_exe.bat

生成发布目录:
.\build_release.bat
python -m py_compile app\ui.py; .\build_release.bat

## Goals
- Import multiple video files
- Choose a preset template
- Add multiple clip ranges per source
- Expand each range into its own output job
- Encode jobs sequentially with progress updates

## Run
Use Python 3.10+ and launch `app/main.py`.

## Build EXE
1. Open PowerShell or cmd in the HandBrakePlus folder.
2. Run `.\build_exe.bat` in PowerShell, or `build_exe.bat` in cmd.
3. After packaging completes, use `dist\HandBrakePlus.exe`.

Notes:
- The build script auto-installs PyInstaller into the active Python environment when needed.
- The exe uses `assets/handbrakeplus.ico` as its Windows icon.
- `config.json` and `session.json` are still written next to the exe at runtime.
- HandBrakeCLI is not bundled; configure its path in the app after first launch.

## HandBrakeCLI Licensing And Distribution
- This project is a desktop wrapper for a locally installed HandBrakeCLI.
- This repository and the generated release folder do not bundle, mirror, or redistribute HandBrakeCLI unless explicitly stated otherwise.
- Users should install HandBrakeCLI separately from official sources and then configure its path in HandBrakePlus.
- If you distribute HandBrakeCLI together with this app, you are responsible for complying with HandBrake and any upstream license terms, including GPL obligations where applicable.
- Keeping this repository public is generally compatible with this setup because the project code here is separate from the HandBrakeCLI binary distribution.

## Build Release Folder
1. Run `.\build_release.bat` in PowerShell, or `build_release.bat` in cmd.
2. Use the generated folder `release\HandBrakePlus` for distribution.

The release folder includes:
- `HandBrakePlus.exe`
- `README.md`
- `config.example.json`
