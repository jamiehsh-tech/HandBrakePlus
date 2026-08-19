"""Tkinter drag-and-drop compatibility helpers.

中文说明：提供 TkinterDnD 可选支持，并在未安装时回退到普通 Tk 窗口。
"""

from __future__ import annotations

import tkinter as tk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

BaseTk = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk
