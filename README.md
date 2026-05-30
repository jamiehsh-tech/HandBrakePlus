# HandBrakePlus

A small Windows desktop batch encoder for HandBrakeCLI.

安装必要文件:
Set-Location "path\to\HandBrakePlus"
python.exe -m pip install -r requirements.txt

启动程序,终端执行: python.exe main.py

打包 exe:
build_exe.bat

生成发布目录:
build_release.bat
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
2. Run `build_exe.bat`.
3. After packaging completes, use `dist\HandBrakePlus.exe`.

Notes:
- The build script auto-installs PyInstaller into the active Python environment when needed.
- The exe uses `assets/handbrakeplus.ico` as its Windows icon.
- `config.json` and `session.json` are still written next to the exe at runtime.
- HandBrakeCLI is not bundled; configure its path in the app after first launch.

## Build Release Folder
1. Run `build_release.bat`.
2. Use the generated folder `release\HandBrakePlus` for distribution.

The release folder includes:
- `HandBrakePlus.exe`
- `README.md`
- `config.example.json`
