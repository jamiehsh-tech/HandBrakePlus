"""Tkinter user interface entry point for HandBrakePlus.

中文说明：HandBrakePlus 的界面入口，负责组合各个 UI 功能模块并初始化应用状态。
"""

from __future__ import annotations

import queue
import sys
from pathlib import Path
import tkinter as tk

from .config_store import ConfigStore
from .handbrake_cli import SourceScanResult
from .models import EncodeJob, JobProgress, VideoSource
from .queue_service import SequentialJobQueue
from .session_store import SessionStore
from .ui_constants import FULL_VIEW_MODE, NORMAL_MIN_WINDOW_SIZE, VALID_VIEW_MODES
from .ui_media import MediaMixin
from .ui_operations import OperationsMixin
from .ui_runtime import RuntimeMixin
from .ui_support import BaseTk, TkinterDnD
from .ui_window import WindowMixin


class HandBrakePlusApp(WindowMixin, MediaMixin, OperationsMixin, RuntimeMixin, BaseTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("HandBrakePlus")
        self._app_icon: tk.PhotoImage | None = None
        self._apply_app_icon()
        self.geometry("1680x980")
        self.minsize(*NORMAL_MIN_WINDOW_SIZE)
        self._configure_scaling()

        self.project_root = self._storage_root()
        self.config_store = ConfigStore(self.project_root)
        self.session_store = SessionStore(self.project_root)
        self.settings = self.config_store.load()
        self.presets = self.config_store.deserialize_presets(self.settings)

        self.sources: list[VideoSource] = []
        self.batch_jobs: list[EncodeJob] = []
        self.selected_source_index: int | None = None
        self.selected_range_index: int | None = None
        self.progress_events: "queue.Queue[JobProgress]" = queue.Queue()
        self.probe_events: "queue.Queue[tuple[str, SourceScanResult | None, str]]" = queue.Queue()
        self.merge_events: "queue.Queue[tuple[Path | None, str]]" = queue.Queue()
        self.job_queue: SequentialJobQueue | None = None
        self.merge_input_paths: list[Path] = []
        self.merge_completed_paths: set[Path] = set()
        self.merge_pending_paths: list[Path] = []

        self.handbrake_path_var = tk.StringVar(value=self.settings["handbrake_path"])
        self.ffmpeg_path_var = tk.StringVar(value=self.settings.get("ffmpeg_path", ""))
        self.output_dir_var = tk.StringVar(value=self.settings.get("default_output_dir", ""))
        self.preset_var = tk.StringVar(value=self.settings.get("last_preset", self.presets[0].name if self.presets else ""))
        initial_view_mode = self.settings.get("last_view_mode", FULL_VIEW_MODE)
        if initial_view_mode not in VALID_VIEW_MODES:
            initial_view_mode = FULL_VIEW_MODE
        self.start_frame_var = tk.StringVar(value="")
        self.end_frame_var = tk.StringVar(value="")
        self.frame_count_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.StringVar(value="0%")
        self.queue_var = tk.StringVar(value="Queue: 0 jobs")
        self.current_job_var = tk.StringVar(value="Current job: none")
        self.source_info_var = tk.StringVar(value="No source selected")
        self.view_mode_var = tk.StringVar(value=initial_view_mode)
        self.current_view_mode = FULL_VIEW_MODE
        self._pre_compact_geometry: str | None = None
        self._pre_compact_window_state: str | None = None
        self.drop_hint_var = tk.StringVar(
            value="Drop videos, MKA audio, or folders here" if TkinterDnD is not None else "Drag-and-drop requires tkinterdnd2; use Add videos for now"
        )
        self.start_frame_var.trace_add("write", self._on_start_frame_changed)
        self.end_frame_var.trace_add("write", self._on_end_frame_changed)

        self._build_ui()
        self._load_session()
        self._refresh_sources_view()
        self._refresh_ranges_view()
        self._refresh_jobs_view()
        self.after(150, self._poll_progress_events)
