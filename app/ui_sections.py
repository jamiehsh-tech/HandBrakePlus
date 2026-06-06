"""UI section builders for the HandBrakePlus main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui import HandBrakePlusApp


class SourceSection:
    """Build the source import section and expose its widgets on the app."""

    def __init__(self, parent: ttk.Frame) -> None:
        self.frame = ttk.LabelFrame(parent, text="1. Import videos")

    def build(self, controller: HandBrakePlusApp) -> ttk.LabelFrame:
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        button_bar = ttk.Frame(self.frame)
        button_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(button_bar, text="Add videos", command=controller._add_videos).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Import list", command=controller._import_sources_from_file).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Export list", command=controller._export_sources_to_file).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Remove selected", command=controller._remove_selected_source).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Add current source to batch", command=controller._add_current_source_to_batch).pack(side="left")

        controller.source_listbox = tk.Listbox(self.frame, height=8, exportselection=False)
        controller.source_listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        controller.source_listbox.bind("<<ListboxSelect>>", controller._on_source_selected)
        controller.source_listbox.bind("<Delete>", controller._on_delete_source_key)

        ttk.Label(self.frame, textvariable=controller.source_info_var).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Label(self.frame, textvariable=controller.drop_hint_var).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))
        controller.source_frame = self.frame
        return self.frame


class RangeSection:
    """Build the clip range section and expose its widgets on the app."""

    def __init__(self, parent: ttk.Frame) -> None:
        self.frame = ttk.LabelFrame(parent, text="2. Clip ranges")

    def build(self, controller: HandBrakePlusApp) -> ttk.LabelFrame:
        self.frame.columnconfigure(2, weight=1)
        self.frame.rowconfigure(2, weight=1)

        ttk.Label(self.frame, text="Frame range").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        range_inputs_frame = ttk.Frame(self.frame)
        range_inputs_frame.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        ttk.Entry(range_inputs_frame, textvariable=controller.start_frame_var, width=12).pack(side="left")
        ttk.Entry(range_inputs_frame, textvariable=controller.end_frame_var, width=12).pack(side="left", padx=(4, 0))
        ttk.Button(range_inputs_frame, text="Clear", command=controller._clear_range_inputs).pack(side="left", padx=(8, 0))

        range_top_actions_frame = ttk.Frame(self.frame)
        range_top_actions_frame.grid(row=0, column=2, sticky="w", padx=(4, 8), pady=6)
        ttk.Button(range_top_actions_frame, text="Full video", command=controller._fill_full_video_range).pack(side="left", padx=(0, 8))
        ttk.Button(range_top_actions_frame, text="Sort", command=controller._sort_ranges).pack(side="left", padx=(0, 8))
        ttk.Button(range_top_actions_frame, text="Clear source", command=controller._clear_ranges).pack(side="left")

        ttk.Label(self.frame, text="Frame count").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.frame, textvariable=controller.frame_count_var, width=16, state="readonly").grid(row=1, column=1, sticky="w", padx=8, pady=6)

        range_bottom_actions_frame = ttk.Frame(self.frame)
        range_bottom_actions_frame.grid(row=1, column=2, sticky="w", padx=(4, 8), pady=6)
        ttk.Button(range_bottom_actions_frame, text="Add range", command=controller._add_range_to_source).pack(side="left", padx=(0, 8))
        ttk.Button(range_bottom_actions_frame, text="Update selected", command=controller._update_selected_range).pack(side="left", padx=(0, 8))
        ttk.Button(range_bottom_actions_frame, text="Remove selected", command=controller._remove_selected_range).pack(side="left", padx=(0, 8))
        ttk.Button(range_bottom_actions_frame, text="Queue selected", command=controller._add_selected_range_to_batch).pack(side="left")

        controller.range_listbox = tk.Listbox(self.frame, height=16, exportselection=False)
        controller.range_listbox.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=8, pady=(0, 8))
        controller.range_listbox.bind("<<ListboxSelect>>", controller._on_range_selected)
        controller.range_listbox.bind("<Delete>", controller._on_delete_range_key)
        controller.range_frame = self.frame
        return self.frame


class QueueSection:
    """Build the batch queue section and expose its widgets on the app."""

    def __init__(self, parent: ttk.Frame) -> None:
        self.frame = ttk.LabelFrame(parent, text="3. Batch queue")

    def build(self, controller: HandBrakePlusApp) -> ttk.LabelFrame:
        self.frame.rowconfigure(1, weight=1)
        self.frame.columnconfigure(0, weight=1)

        button_bar = ttk.Frame(self.frame)
        button_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(button_bar, text="Add selected source ranges", command=controller._add_current_source_to_batch).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Add selected range", command=controller._add_selected_range_to_batch).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Add all sources", command=controller._add_all_sources_to_batch).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Delete selected", command=controller._remove_selected_jobs).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Clear queue", command=controller._clear_queue).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Start encoding", command=controller._start_encoding).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Stop", command=controller._stop_queue).pack(side="left")

        controller.queue_tree = ttk.Treeview(self.frame, columns=("source", "range", "output", "preset"), show="headings", height=13, selectmode="extended")
        for column, width in (("source", 220), ("range", 120), ("output", 360), ("preset", 180)):
            controller.queue_tree.heading(column, text=column.title())
            controller.queue_tree.column(column, width=width, anchor="w")
        controller.queue_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        controller.queue_tree.bind("<Delete>", controller._on_delete_jobs_key)
        controller.queue_frame = self.frame
        return self.frame


class ProgressSection:
    """Build the progress and log sections and expose their widgets on the app."""

    def __init__(self, parent: ttk.Frame) -> None:
        self.progress_frame = ttk.LabelFrame(parent, text="4. Progress")
        self.log_frame = ttk.LabelFrame(parent, text="Logs")

    def build(self, controller: HandBrakePlusApp) -> tuple[ttk.LabelFrame, ttk.LabelFrame]:
        self.progress_frame.columnconfigure(0, weight=1)
        ttk.Label(self.progress_frame, textvariable=controller.current_job_var).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(self.progress_frame, textvariable=controller.progress_var).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))
        ttk.Label(self.progress_frame, textvariable=controller.queue_var).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))

        self.log_frame.rowconfigure(0, weight=1)
        self.log_frame.columnconfigure(0, weight=1)
        controller.log_text = tk.Text(self.log_frame, height=24, wrap="word")
        controller.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(self.log_frame, orient="vertical", command=controller.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        controller.log_text.configure(yscrollcommand=scrollbar.set)

        controller.progress_frame = self.progress_frame
        controller.log_frame = self.log_frame
        return self.progress_frame, self.log_frame
