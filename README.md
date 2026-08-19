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
- Use the built-in `Audio only - source copy` preset to extract all embedded audio tracks with FFmpeg stream copy (no video re-encoding; outputs `.mka`).
- Import `.mka` files as audio sources; their editing timeline uses milliseconds and can be exported with the audio-only preset.
- For `.mka` ranges, paste `HH:MM:SS.mmm` such as `00:00:03.616`; the field converts it to milliseconds automatically.
- Select `Merge mode` in the View bar to open the standalone merge page. Add or drag video/audio files, reorder them, and concatenate same-extension inputs; the generated output name is `first-file-name-merge.ext`.
- Add multiple clip ranges per source
- Expand each range into its own output job
- Encode jobs sequentially with progress updates

## 音频导出说明

选择 Preset 中的 `Audio only - source copy` 后，HandBrakePlus 会调用 FFmpeg：

- 只读取视频文件内的音频轨道，不导出视频画面。
- 使用音频流复制，不重新编码，因此尽量保留原始编码、码率和音质。
- 视频中的多个音频轨道会全部导出。
- 输出文件为 `.mka`，适合容纳不同类型的原始音频流。
- 在 Config 的 `FFmpeg (audio preset)` 中选择 `ffmpeg.exe`；如果 FFmpeg 已加入系统 PATH，可以留空。
- 当前选择的帧范围会按视频帧率换算为音频时间范围后导出。

如果需要将音频转换成 AAC、MP3 等格式，请使用其他支持音频编码的工具或后续增加转码 Preset；当前 Preset 的目标是原音频复制。

## Run
Use Python 3.10+ and launch the root `main.py`.

## VS Code Run And Debug
Open the HandBrakePlus folder as the workspace, select the desired Python interpreter, then press `F5` and choose `Python: HandBrakePlus`. The launch configuration runs the root `main.py` with the project root as its working directory, so local `config.json` and `session.json` are resolved correctly. Breakpoints can be placed in `app/ui.py`, `app/handbrake_cli.py`, and other application modules.

## Build EXE
1. Open PowerShell or cmd in the HandBrakePlus folder.
2. Run `.\build_exe.bat` in PowerShell, or `build_exe.bat` in cmd.
3. After packaging completes, use `dist\HandBrakePlus.exe`.

Notes:
- The build script auto-installs PyInstaller into the active Python environment when needed.
- The exe uses `assets/handbrakeplus.ico` as its Windows icon.
- `config.json` and `session.json` are still written next to the exe at runtime.
- HandBrakeCLI is not bundled; configure its path in the app after first launch.
- FFmpeg is required for the audio-only preset; configure `ffmpeg.exe` in the app or make it available on `PATH`.

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
