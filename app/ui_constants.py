"""Shared UI constants.

中文说明：集中保存界面模式、窗口尺寸、媒体扩展名和时间码转换等共享常量。
"""

from __future__ import annotations

import re

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".ts", ".m4v", ".mka"}
MIN_FOLDER_IMPORT_SIZE_BYTES = 100 * 1024 * 1024
NORMAL_MIN_WINDOW_SIZE = (2700, 1280)
# Full mode 全屏模式的左右区域宽度比例。数值越大，分到的横向空间越多。
# 例如 2:3 表示左侧约占 40%，右侧约占 60%；想改变比例时只修改这里。
FULL_LEFT_PANEL_WEIGHT = 5
FULL_RIGHT_PANEL_WEIGHT = 4
COMPACT_MIN_WINDOW_SIZE = (720, 420)
COMPACT_WINDOW_SIZE = (980, 620)
LEFT_ONLY_MIN_WINDOW_SIZE = (1280, 1280)
LEFT_ONLY_WINDOW_SIZE = (1480, 1280)
MERGE_MIN_WINDOW_SIZE = (720, 520)
MERGE_WINDOW_SIZE = (1280, 720)
FULL_VIEW_MODE = "full"
IMPORT_ONLY_VIEW_MODE = "compact_import"
LEFT_ONLY_VIEW_MODE = "compact_left"
MERGE_VIEW_MODE = "merge"
VALID_VIEW_MODES = {FULL_VIEW_MODE, IMPORT_ONLY_VIEW_MODE, LEFT_ONLY_VIEW_MODE, MERGE_VIEW_MODE}
TIME_CODE_PATTERN = re.compile(r"^(?P<hours>\\d+):(?P<minutes>[0-5]\\d):(?P<seconds>[0-5]\\d)(?:\\.(?P<milliseconds>\\d{1,3}))?$")
