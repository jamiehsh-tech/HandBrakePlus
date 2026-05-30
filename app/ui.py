"""Tkinter user interface for HandBrakePlus batch encoding."""

from __future__ import annotations

import queue
import sys
import threading
import json
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .config_store import ConfigStore
from .handbrake_cli import HandBrakeRunner, HandBrakeSettings
from .models import ClipRange, EncodeJob, JobProgress, PresetTemplate, VideoSource
from .queue_service import SequentialJobQueue
from .session_store import SessionStore

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None


BaseTk = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".ts", ".m4v"}
MIN_FOLDER_IMPORT_SIZE_BYTES = 100 * 1024 * 1024
NORMAL_MIN_WINDOW_SIZE = (2800, 1280)
COMPACT_MIN_WINDOW_SIZE = (720, 420)
COMPACT_WINDOW_SIZE = (980, 620)


class HandBrakePlusApp(BaseTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("HandBrakePlus")
        self._app_icon: tk.PhotoImage | None = None
        self._apply_app_icon()
        self.geometry("1680x980")
        self.minsize(*NORMAL_MIN_WINDOW_SIZE)
        self._configure_scaling()

        self.project_root = Path(__file__).resolve().parent.parent
        self.config_store = ConfigStore(self.project_root)
        self.session_store = SessionStore(self.project_root)
        self.settings = self.config_store.load()
        self.presets = self.config_store.deserialize_presets(self.settings)

        self.sources: list[VideoSource] = []
        self.batch_jobs: list[EncodeJob] = []
        self.selected_source_index: int | None = None
        self.selected_range_index: int | None = None
        self.progress_events: "queue.Queue[JobProgress]" = queue.Queue()
        self.probe_events: "queue.Queue[tuple[str, int | None, str]]" = queue.Queue()
        self.job_queue: SequentialJobQueue | None = None

        self.handbrake_path_var = tk.StringVar(value=self.settings["handbrake_path"])
        self.output_dir_var = tk.StringVar(value=self.settings.get("default_output_dir", ""))
        self.preset_var = tk.StringVar(value=self.settings.get("last_preset", self.presets[0].name if self.presets else ""))
        self.start_frame_var = tk.StringVar(value="")
        self.end_frame_var = tk.StringVar(value="")
        self.frame_count_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.StringVar(value="0%")
        self.queue_var = tk.StringVar(value="Queue: 0 jobs")
        self.current_job_var = tk.StringVar(value="Current job: none")
        self.source_info_var = tk.StringVar(value="No source selected")
        self.compact_import_mode = False
        self.compact_import_button_var = tk.StringVar(value="Compact mode")
        self._pre_compact_geometry: str | None = None
        self._pre_compact_window_state: str | None = None
        self.drop_hint_var = tk.StringVar(
            value="Drop videos or folders here; folder import keeps videos over 100 MB" if TkinterDnD is not None else "Drag-and-drop requires tkinterdnd2; use Add videos for now"
        )
        self.start_frame_var.trace_add("write", self._on_start_frame_changed)
        self.end_frame_var.trace_add("write", self._on_end_frame_changed)

        self._build_ui()
        self._load_session()
        self._refresh_sources_view()
        self._refresh_ranges_view()
        self._refresh_jobs_view()
        self.after(150, self._poll_progress_events)

    def _resource_root(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return Path(__file__).resolve().parent.parent

    def _apply_app_icon(self) -> None:
        icon_path = self._resource_root() / "assets" / "handbrakeplus.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
                return
            except tk.TclError:
                pass

        self._app_icon = self._create_app_icon()
        if self._app_icon is not None:
            self.iconphoto(True, self._app_icon)

    def _create_app_icon(self) -> tk.PhotoImage | None:
        palette = {
            ".": "24 24 27",
            "o": "241 94 34",
            "x": "255 138 76",
            "w": "250 250 250",
            "k": "15 15 18",
        }
        pixels = [
            "................",
            "....oooooooo....",
            "..ooxxxxxxxxo...",
            ".ooxkkkkkkkkxo..",
            ".oxkwwk..kwwkxo.",
            "oxxkwwk..kwwkxxo",
            "oxxkwwkkkkwwkxxo",
            "oxxkwwkkkkwwkxxo",
            "oxxkwwkwwwwwkxxo",
            "oxxkwwkkkkwwkxxo",
            "oxxkwwkkkkwwkxxo",
            ".oxkwwk..kwwkxo.",
            ".ooxkkkkkkkkxo..",
            "..ooxxxxxxxxo...",
            "....oooooooo....",
            "................",
        ]
        header = f"P3\n16 16\n255\n"
        body = "\n".join(" ".join(palette[pixel] for pixel in row) for row in pixels)
        try:
            return tk.PhotoImage(data=header + body, format="PPM")
        except tk.TclError:
            return None

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.config_frame = ttk.LabelFrame(self, text="Config")
        self.config_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        self.config_frame.columnconfigure(1, weight=1)
        self.config_frame.columnconfigure(4, weight=1)
        self.config_frame.columnconfigure(5, weight=1)

        ttk.Label(self.config_frame, text="HandBrakeCLI").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.config_frame, textvariable=self.handbrake_path_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        ttk.Button(self.config_frame, text="Browse", command=self._browse_handbrake).grid(row=0, column=4, sticky="ew", padx=8, pady=6)

        ttk.Label(self.config_frame, text="Output folder").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.config_frame, textvariable=self.output_dir_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        ttk.Button(self.config_frame, text="Browse", command=self._browse_output_dir).grid(row=1, column=4, sticky="ew", padx=8, pady=6)

        ttk.Label(self.config_frame, text="Preset").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        preset_values = [preset.name for preset in self.presets]
        self.preset_combo = ttk.Combobox(self.config_frame, textvariable=self.preset_var, values=preset_values, state="readonly")
        self.preset_combo.grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_preset_changed())
        ttk.Button(self.config_frame, text="Edit presets", command=self._open_preset_editor).grid(row=2, column=2, sticky="w", padx=8, pady=6)
        ttk.Label(self.config_frame, textvariable=self.status_var).grid(row=2, column=3, columnspan=3, sticky="w", padx=8, pady=6)

        self.main_frame = ttk.Frame(self)
        self.main_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=0)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

        self.left_panel = ttk.Frame(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.left_panel.rowconfigure(0, weight=0)
        self.left_panel.rowconfigure(1, weight=2)
        self.left_panel.columnconfigure(0, weight=1)

        self.source_frame = ttk.LabelFrame(self.left_panel, text="1. Import videos")
        self.source_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.source_frame.columnconfigure(0, weight=1)
        self.source_frame.rowconfigure(1, weight=1)

        source_button_bar = ttk.Frame(self.source_frame)
        source_button_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(source_button_bar, textvariable=self.compact_import_button_var, command=self._toggle_compact_import_mode).pack(side="left", padx=(8, 0))
        ttk.Button(source_button_bar, text="Import list", command=self._import_sources_from_file).pack(side="left", padx=(0, 8))
        ttk.Button(source_button_bar, text="Export list", command=self._export_sources_to_file).pack(side="left", padx=(0, 8))
        ttk.Button(source_button_bar, text="Remove selected", command=self._remove_selected_source).pack(side="left", padx=(0, 8))
        ttk.Button(source_button_bar, text="Add current source to batch", command=self._add_current_source_to_batch).pack(side="left")
        ttk.Button(source_button_bar, text="Add videos", command=self._add_videos).pack(side="left", padx=(0, 8))

        self.source_listbox = tk.Listbox(self.source_frame, height=8, exportselection=False)
        self.source_listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.source_listbox.bind("<<ListboxSelect>>", self._on_source_selected)
        self.source_listbox.bind("<Delete>", self._on_delete_source_key)
        ttk.Label(self.source_frame, textvariable=self.source_info_var).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Label(self.source_frame, textvariable=self.drop_hint_var).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

        if TkinterDnD is not None and DND_FILES is not None:
            self.source_listbox.drop_target_register(DND_FILES)
            self.source_listbox.dnd_bind("<<Drop>>", self._on_files_dropped)

        self.range_frame = ttk.LabelFrame(self.left_panel, text="2. Clip ranges")
        self.range_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.range_frame.columnconfigure(7, weight=1)
        self.range_frame.rowconfigure(2, weight=1)

        ttk.Label(self.range_frame, text="Frame range").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        range_inputs_frame = ttk.Frame(self.range_frame)
        range_inputs_frame.grid(row=0, column=1, columnspan=2, sticky="w", padx=8, pady=6)
        ttk.Entry(range_inputs_frame, textvariable=self.start_frame_var, width=12).pack(side="left")
        ttk.Entry(range_inputs_frame, textvariable=self.end_frame_var, width=12).pack(side="left", padx=(4, 0))
        ttk.Button(range_inputs_frame, text="Clear", command=self._clear_range_inputs).pack(side="left", padx=(8, 0))
        ttk.Button(self.range_frame, text="Sort", command=self._sort_ranges).grid(row=0, column=4, sticky="w", padx=8, pady=6)
        ttk.Button(self.range_frame, text="Clear source", command=self._clear_ranges).grid(row=0, column=5, sticky="w", padx=8, pady=6)
        ttk.Label(self.range_frame, text="Frame count").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.range_frame, textvariable=self.frame_count_var, width=16, state="readonly").grid(row=1, column=1, sticky="w", padx=8, pady=6)
        ttk.Button(self.range_frame, text="Add range", command=self._add_range_to_source).grid(row=1, column=2, sticky="w", padx=8, pady=6)
        ttk.Button(self.range_frame, text="Update selected", command=self._update_selected_range).grid(row=1, column=3, sticky="w", padx=8, pady=6)
        ttk.Button(self.range_frame, text="Remove selected", command=self._remove_selected_range).grid(row=1, column=4, sticky="w", padx=8, pady=6)
        ttk.Button(self.range_frame, text="Queue selected", command=self._add_selected_range_to_batch).grid(row=1, column=5, sticky="w", padx=8, pady=6)

        self.range_listbox = tk.Listbox(self.range_frame, height=16, exportselection=False)
        self.range_listbox.grid(row=2, column=0, columnspan=8, sticky="nsew", padx=8, pady=(0, 8))
        self.range_listbox.bind("<<ListboxSelect>>", self._on_range_selected)
        self.range_listbox.bind("<Delete>", self._on_delete_range_key)

        self.right_panel = ttk.Frame(self.main_frame)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.right_panel.rowconfigure(0, weight=2)
        self.right_panel.rowconfigure(1, weight=0)
        self.right_panel.rowconfigure(2, weight=1)
        self.right_panel.columnconfigure(0, weight=1)

        queue_frame = ttk.LabelFrame(self.right_panel, text="3. Batch queue")
        queue_frame.grid(row=0, column=0, sticky="nsew")
        queue_frame.rowconfigure(1, weight=1)
        queue_frame.columnconfigure(0, weight=1)

        queue_button_bar = ttk.Frame(queue_frame)
        queue_button_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(queue_button_bar, text="Add selected source ranges", command=self._add_current_source_to_batch).pack(side="left", padx=(0, 8))
        ttk.Button(queue_button_bar, text="Add selected range", command=self._add_selected_range_to_batch).pack(side="left", padx=(0, 8))
        ttk.Button(queue_button_bar, text="Add all sources", command=self._add_all_sources_to_batch).pack(side="left", padx=(0, 8))
        ttk.Button(queue_button_bar, text="Delete selected", command=self._remove_selected_jobs).pack(side="left", padx=(0, 8))
        ttk.Button(queue_button_bar, text="Clear queue", command=self._clear_queue).pack(side="left", padx=(0, 8))
        ttk.Button(queue_button_bar, text="Start encoding", command=self._start_encoding).pack(side="left", padx=(0, 8))
        ttk.Button(queue_button_bar, text="Stop", command=self._stop_queue).pack(side="left")

        self.queue_tree = ttk.Treeview(queue_frame, columns=("source", "range", "output", "preset"), show="headings", height=13, selectmode="extended")
        for column, width in (("source", 220), ("range", 120), ("output", 360), ("preset", 180)):
            self.queue_tree.heading(column, text=column.title())
            self.queue_tree.column(column, width=width, anchor="w")
        self.queue_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.queue_tree.bind("<Delete>", self._on_delete_jobs_key)

        progress_frame = ttk.LabelFrame(self.right_panel, text="4. Progress")
        progress_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        progress_frame.columnconfigure(0, weight=1)

        ttk.Label(progress_frame, textvariable=self.current_job_var).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(progress_frame, textvariable=self.progress_var).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))
        ttk.Label(progress_frame, textvariable=self.queue_var).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))

        log_frame = ttk.LabelFrame(self.right_panel, text="Logs")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=24, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _browse_handbrake(self) -> None:
        path = filedialog.askopenfilename(title="Select HandBrakeCLI.exe", filetypes=(("Executable", "*.exe"), ("All files", "*.*")))
        if path:
            self.handbrake_path_var.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir_var.set(path)

    def _on_preset_changed(self) -> None:
        preset = self._selected_preset()
        if preset:
            self._log(f"Preset selected: {preset.name} - {preset.description}")

    def _set_presets(self, presets: list[PresetTemplate]) -> None:
        self.presets = presets
        preset_names = [preset.name for preset in self.presets]
        self.preset_combo.configure(values=preset_names)
        if self.preset_var.get() not in preset_names and preset_names:
            self.preset_var.set(preset_names[0])

    def _open_preset_editor(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Edit presets")
        dialog.geometry("960x620")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(0, weight=1)

        preset_items = [
            {
                "name": preset.name,
                "description": preset.description,
                "handbrake_args": list(preset.handbrake_args),
            }
            for preset in self.presets
        ]

        list_frame = ttk.Frame(dialog)
        list_frame.grid(row=0, column=0, sticky="ns", padx=(12, 8), pady=12)
        list_frame.rowconfigure(1, weight=1)
        ttk.Label(list_frame, text="Presets").grid(row=0, column=0, sticky="w")

        preset_listbox = tk.Listbox(list_frame, height=20, exportselection=False, width=32)
        preset_listbox.grid(row=1, column=0, sticky="ns")

        editor_frame = ttk.Frame(dialog)
        editor_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=12)
        editor_frame.columnconfigure(1, weight=1)
        editor_frame.rowconfigure(5, weight=1)

        name_var = tk.StringVar()
        description_var = tk.StringVar()

        ttk.Label(editor_frame, text="Name").grid(row=0, column=0, sticky="w", pady=(0, 8))
        name_entry = ttk.Entry(editor_frame, textvariable=name_var)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(editor_frame, text="Description").grid(row=1, column=0, sticky="w", pady=(0, 8))
        description_entry = ttk.Entry(editor_frame, textvariable=description_var)
        description_entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(editor_frame, text="HandBrake args").grid(row=2, column=0, sticky="nw", pady=(0, 8))
        args_text = tk.Text(editor_frame, height=18, wrap="word")
        args_text.grid(row=2, column=1, sticky="nsew", pady=(0, 8))

        ttk.Label(
            editor_frame,
            text="One argument per line, or paste space-separated arguments. Example: --encoder nvenc_h265",
        ).grid(row=3, column=1, sticky="w", pady=(0, 8))

        button_bar = ttk.Frame(editor_frame)
        button_bar.grid(row=4, column=1, sticky="w", pady=(0, 8))

        def refresh_preset_list(selected_index: int | None = None) -> None:
            preset_listbox.delete(0, tk.END)
            for item in preset_items:
                preset_listbox.insert(tk.END, item["name"])
            if preset_items:
                target_index = selected_index if selected_index is not None else 0
                target_index = max(0, min(target_index, len(preset_items) - 1))
                preset_listbox.selection_clear(0, tk.END)
                preset_listbox.selection_set(target_index)
                preset_listbox.activate(target_index)
                load_preset(target_index)
            else:
                name_var.set("")
                description_var.set("")
                args_text.delete("1.0", tk.END)

        def parse_args() -> list[str]:
            raw_value = args_text.get("1.0", tk.END).strip()
            if not raw_value:
                return []
            if "\n" in raw_value:
                return [line.strip() for line in raw_value.splitlines() if line.strip()]
            return [part for part in raw_value.split(" ") if part]

        def load_preset(index: int) -> None:
            if index < 0 or index >= len(preset_items):
                return
            item = preset_items[index]
            name_var.set(item["name"])
            description_var.set(item.get("description", ""))
            args_text.delete("1.0", tk.END)
            args_text.insert("1.0", "\n".join(item.get("handbrake_args", [])))

        def current_index() -> int | None:
            selection = preset_listbox.curselection()
            if not selection:
                return None
            return selection[0]

        def save_current_preset() -> None:
            index = current_index()
            if index is None:
                return
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Invalid preset", "Preset name is required.", parent=dialog)
                return
            preset_items[index] = {
                "name": name,
                "description": description_var.get().strip(),
                "handbrake_args": parse_args(),
            }
            refresh_preset_list(index)

        def add_preset() -> None:
            preset_items.append({"name": "New preset", "description": "", "handbrake_args": []})
            refresh_preset_list(len(preset_items) - 1)

        def delete_preset() -> None:
            index = current_index()
            if index is None:
                return
            del preset_items[index]
            refresh_preset_list(index)

        def save_all_presets() -> None:
            normalized: list[dict[str, object]] = []
            seen_names: set[str] = set()
            for item in preset_items:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                if name in seen_names:
                    messagebox.showerror("Duplicate preset", f"Preset name '{name}' appears more than once.", parent=dialog)
                    return
                seen_names.add(name)
                normalized.append(
                    {
                        "name": name,
                        "description": str(item.get("description", "")).strip(),
                        "handbrake_args": list(item.get("handbrake_args", [])),
                    }
                )
            if not normalized:
                messagebox.showerror("No presets", "At least one preset is required.", parent=dialog)
                return
            self.settings["presets"] = normalized
            if self.preset_var.get() not in seen_names:
                self.preset_var.set(normalized[0]["name"])
            self.config_store.save(self.settings)
            self.settings = self.config_store.load()
            self._set_presets(self.config_store.deserialize_presets(self.settings))
            self._on_preset_changed()
            dialog.destroy()

        ttk.Button(button_bar, text="Save current", command=save_current_preset).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="New", command=add_preset).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Delete", command=delete_preset).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Save all", command=save_all_presets).pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Close", command=dialog.destroy).pack(side="left")

        preset_listbox.bind("<<ListboxSelect>>", lambda _event: load_preset(current_index() or 0))
        refresh_preset_list()

    def _selected_preset(self) -> PresetTemplate | None:
        for preset in self.presets:
            if preset.name == self.preset_var.get():
                return preset
        return self.presets[0] if self.presets else None

    def _configure_scaling(self) -> None:
        scaling = self.winfo_fpixels("1i") / 72.0
        self.tk.call("tk", "scaling", scaling)

        default_font = tkfont.nametofont("TkDefaultFont")
        text_font = tkfont.nametofont("TkTextFont")
        heading_font = tkfont.nametofont("TkHeadingFont")

        default_font.configure(size=max(default_font.cget("size"), 10))
        text_font.configure(size=max(text_font.cget("size"), 10))
        heading_font.configure(size=max(heading_font.cget("size"), 10))

        style = ttk.Style(self)
        row_height = max(28, text_font.metrics("linespace") + 10)
        style.configure("Treeview", rowheight=row_height)

    def _add_videos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select source videos",
            filetypes=(("Video files", "*.mp4 *.mkv *.mov *.avi *.wmv *.ts *.m4v"), ("All files", "*.*")),
        )
        self._import_video_paths(paths)

    def _export_sources_to_file(self) -> None:
        if not self.sources:
            messagebox.showinfo("No videos", "Import at least one video before exporting.")
            return
        selected_path = filedialog.asksaveasfilename(
            title="Export videos and clips",
            defaultextension=".json",
            initialfile="handbrakeplus-videos-and-clips.json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not selected_path:
            return
        try:
            self.session_store.export_sources(Path(selected_path), self.sources)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        self._log(f"Exported {len(self.sources)} video source(s) with clip ranges.")

    def _import_sources_from_file(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="Import videos and clips",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not selected_path:
            return
        try:
            imported_sources = self.session_store.import_sources(Path(selected_path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        if not imported_sources:
            messagebox.showinfo("No videos", "The selected file does not contain any videos to import.")
            return

        existing_index_by_path = {source.path: index for index, source in enumerate(self.sources)}
        added_count = 0
        replaced_count = 0
        runner = self._create_runner_if_available()

        for imported_source in imported_sources:
            self._reindex_ranges(imported_source)
            if imported_source.total_frames is None and not imported_source.probe_error:
                imported_source.probe_error = "Scanning..."
                if runner is not None:
                    threading.Thread(
                        target=self._probe_source_async,
                        args=(imported_source.path, runner),
                        daemon=True,
                    ).start()

            existing_index = existing_index_by_path.get(imported_source.path)
            if existing_index is None:
                self.sources.append(imported_source)
                existing_index_by_path[imported_source.path] = len(self.sources) - 1
                added_count += 1
            else:
                self.sources[existing_index] = imported_source
                replaced_count += 1

        if self.sources:
            first_imported_path = imported_sources[0].path
            self.selected_source_index = existing_index_by_path.get(first_imported_path, 0)
        self.selected_range_index = None
        self._refresh_sources_view()
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Imported {added_count} new video source(s) and refreshed {replaced_count} existing source(s) from file.")

    def _normalize_import_path(self, raw_path: str) -> Path | None:
        candidate = raw_path.strip()
        if not candidate:
            return None
        if candidate.startswith("{") and candidate.endswith("}"):
            candidate = candidate[1:-1]
        if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'"}:
            candidate = candidate[1:-1]

        parsed = urlparse(candidate)
        if parsed.scheme == "file":
            candidate = url2pathname(unquote(parsed.path))
            if parsed.netloc:
                candidate = f"//{parsed.netloc}{candidate}"

        return Path(candidate)

    def _iter_import_candidates(self, paths: tuple[str, ...] | list[str], expand_directories: bool = False) -> list[Path]:
        candidates: list[Path] = []
        for path in paths:
            source_path = self._normalize_import_path(path)
            if source_path is None:
                continue
            if source_path.is_file():
                if source_path.suffix.lower() in VIDEO_EXTENSIONS:
                    candidates.append(source_path)
                continue
            if not expand_directories or not source_path.is_dir():
                continue
            try:
                for nested_path in source_path.rglob("*"):
                    if not nested_path.is_file() or nested_path.suffix.lower() not in VIDEO_EXTENSIONS:
                        continue
                    try:
                        if nested_path.stat().st_size > MIN_FOLDER_IMPORT_SIZE_BYTES:
                            candidates.append(nested_path)
                    except OSError:
                        continue
            except OSError:
                continue
        return candidates

    def _import_video_paths(self, paths: tuple[str, ...] | list[str], expand_directories: bool = False) -> None:
        if not paths:
            return
        existing = {source.path for source in self.sources}
        added_count = 0
        candidate_paths = self._iter_import_candidates(paths, expand_directories=expand_directories)
        runner = self._create_runner_if_available()
        for source_path in candidate_paths:
            if source_path not in existing:
                source = VideoSource(path=source_path)
                source.probe_error = "Scanning..."
                self.sources.append(source)
                if runner is not None:
                    threading.Thread(
                        target=self._probe_source_async,
                        args=(source.path, runner),
                        daemon=True,
                    ).start()
                existing.add(source_path)
                added_count += 1
        if self.selected_source_index is None and self.sources:
            self.selected_source_index = 0
        self.selected_range_index = None
        self._refresh_sources_view()
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Imported {added_count} video(s).")

    def _on_files_dropped(self, event: object) -> None:
        raw_data = getattr(event, "data", "")
        if not raw_data:
            return
        try:
            paths = list(self.tk.splitlist(raw_data))
        except tk.TclError:
            paths = []
        if not paths:
            paths = [raw_data]
        self._import_video_paths(paths, expand_directories=True)

    def _toggle_compact_import_mode(self) -> None:
        self.compact_import_mode = not self.compact_import_mode
        if self.compact_import_mode:
            self.update_idletasks()
            self._pre_compact_geometry = self.geometry()
            self._pre_compact_window_state = self.state()
            if self._pre_compact_window_state == "zoomed":
                self.state("normal")
            self.config_frame.grid_remove()
            self.range_frame.grid_remove()
            self.right_panel.grid_remove()
            self.main_frame.columnconfigure(0, weight=1)
            self.main_frame.columnconfigure(1, weight=0)
            self.left_panel.rowconfigure(0, weight=1)
            self.left_panel.rowconfigure(1, weight=0)
            self.left_panel.grid_configure(padx=0)
            self.source_frame.grid_configure(pady=0)
            self.minsize(*COMPACT_MIN_WINDOW_SIZE)
            self.geometry(f"{COMPACT_WINDOW_SIZE[0]}x{COMPACT_WINDOW_SIZE[1]}")
            self.compact_import_button_var.set("Restore view")
        else:
            self.config_frame.grid()
            self.range_frame.grid()
            self.right_panel.grid()
            self.main_frame.columnconfigure(0, weight=1)
            self.main_frame.columnconfigure(1, weight=1)
            self.left_panel.rowconfigure(0, weight=0)
            self.left_panel.rowconfigure(1, weight=2)
            self.left_panel.grid_configure(padx=(0, 8))
            self.source_frame.grid_configure(pady=(0, 8))
            self.minsize(*NORMAL_MIN_WINDOW_SIZE)
            if self._pre_compact_window_state == "zoomed":
                self.state("zoomed")
            elif self._pre_compact_geometry:
                self.geometry(self._pre_compact_geometry)
            self.compact_import_button_var.set("Compact mode")

    def _on_delete_source_key(self, _event: object) -> str:
        self._remove_selected_source()
        return "break"

    def _on_delete_range_key(self, _event: object) -> str:
        self._remove_selected_range()
        return "break"

    def _on_delete_jobs_key(self, _event: object) -> str:
        self._remove_selected_jobs()
        return "break"

    def _remove_selected_source(self) -> None:
        selection = self.source_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index < 0 or index >= len(self.sources):
            return
        removed = self.sources.pop(index)
        self._log(f"Removed source: {removed.path.name}")
        if not self.sources:
            self.selected_source_index = None
        else:
            self.selected_source_index = min(index, len(self.sources) - 1)
        self.selected_range_index = None
        self._refresh_sources_view()
        self._refresh_ranges_view()
        self._save_session()

    def _on_source_selected(self, _event: object) -> None:
        selection = self.source_listbox.curselection()
        if not selection:
            return
        self.selected_source_index = selection[0]
        self.selected_range_index = None
        self._refresh_ranges_view()

    def _on_range_selected(self, _event: object) -> None:
        selection = self.range_listbox.curselection()
        if not selection:
            return
        self.selected_range_index = selection[0]
        source = self._current_source()
        if source is None or self.selected_range_index >= len(source.ranges):
            return
        clip = source.ranges[self.selected_range_index]
        self.start_frame_var.set(str(clip.start_frame))
        self.end_frame_var.set(str(clip.end_frame))
        self.frame_count_var.set(str(clip.duration_frames))

    def _on_start_frame_changed(self, *_args: object) -> None:
        start_text = self.start_frame_var.get().strip()
        end_text = self.end_frame_var.get().strip()
        if not start_text or not end_text:
            self._update_frame_count_display()
            return
        try:
            start_frame = int(start_text)
            end_frame = int(end_text)
        except ValueError:
            self._update_frame_count_display()
            return
        if start_frame > end_frame:
            self.end_frame_var.set("")
            self.frame_count_var.set("")
            return
        self._update_frame_count_display()

    def _on_end_frame_changed(self, *_args: object) -> None:
        self._update_frame_count_display()

    def _update_frame_count_display(self) -> None:
        start_text = self.start_frame_var.get().strip()
        end_text = self.end_frame_var.get().strip()
        if not start_text or not end_text:
            self.frame_count_var.set("")
            return
        try:
            start_frame = int(start_text)
            end_frame = int(end_text)
        except ValueError:
            self.frame_count_var.set("")
            return
        if end_frame <= start_frame:
            self.frame_count_var.set("")
            return
        self.frame_count_var.set(str(end_frame - start_frame + 1))

    def _clear_range_inputs(self) -> None:
        self.start_frame_var.set("")
        self.end_frame_var.set("")
        self.frame_count_var.set("")

    def _current_source(self) -> VideoSource | None:
        if self.selected_source_index is None:
            return None
        if self.selected_source_index >= len(self.sources):
            return None
        return self.sources[self.selected_source_index]

    def _read_range_inputs(self, source: VideoSource) -> tuple[int, int, int]:
        try:
            start_frame = int(self.start_frame_var.get().strip())
            end_frame = int(self.end_frame_var.get().strip())
            frame_count = end_frame - start_frame + 1
        except ValueError as exc:
            raise ValueError("Start/end frame must be integers.") from exc

        if start_frame < 0 or end_frame <= start_frame:
            raise ValueError("End frame must be greater than start frame.")

        max_frame_index = source.max_frame_index
        if max_frame_index is not None and (start_frame > max_frame_index or end_frame > max_frame_index):
            raise ValueError(f"Frame input exceeds the source limit. Valid frame index range: 0 to {max_frame_index}.")

        return start_frame, end_frame, frame_count

    def _reindex_ranges(self, source: VideoSource) -> None:
        for new_index, clip in enumerate(source.ranges, start=1):
            clip.index = new_index

    def _add_range_to_source(self) -> None:
        source = self._current_source()
        if source is None:
            messagebox.showwarning("No source", "Please import and select a video first.")
            return
        try:
            start_frame, end_frame, frame_count = self._read_range_inputs(source)
        except ValueError as exc:
            title = "Out of range" if "source limit" in str(exc) else "Invalid range"
            messagebox.showerror(title, str(exc))
            return
        clip = ClipRange(start_frame=start_frame, end_frame=end_frame, index=len(source.ranges) + 1, frame_count=frame_count)
        source.ranges.append(clip)
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Added range for {source.path.name}: {clip.start_frame} - {clip.end_frame}")

    def _update_selected_range(self) -> None:
        source = self._current_source()
        if source is None:
            messagebox.showwarning("No source", "Please import and select a video first.")
            return
        selection = self.range_listbox.curselection()
        if not selection:
            messagebox.showwarning("No range", "Select a range from the source first.")
            return
        index = selection[0]
        if index < 0 or index >= len(source.ranges):
            return
        try:
            start_frame, end_frame, frame_count = self._read_range_inputs(source)
        except ValueError as exc:
            title = "Out of range" if "source limit" in str(exc) else "Invalid range"
            messagebox.showerror(title, str(exc))
            return
        clip = source.ranges[index]
        clip.start_frame = start_frame
        clip.end_frame = end_frame
        clip.frame_count = frame_count
        self.selected_range_index = index
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Updated range {clip.index} for {source.path.name}: {clip.start_frame} - {clip.end_frame}")

    def _sort_ranges(self) -> None:
        source = self._current_source()
        if source is None:
            return
        if len(source.ranges) < 2:
            return
        selected_clip: ClipRange | None = None
        if self.selected_range_index is not None and 0 <= self.selected_range_index < len(source.ranges):
            selected_clip = source.ranges[self.selected_range_index]
        source.ranges.sort(key=lambda clip: (clip.start_frame, clip.end_frame))
        self._reindex_ranges(source)
        if selected_clip is not None:
            self.selected_range_index = source.ranges.index(selected_clip)
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Sorted {len(source.ranges)} range(s) for {source.path.name} by start frame.")

    def _clear_ranges(self) -> None:
        source = self._current_source()
        if source is None:
            return
        source.ranges.clear()
        self.selected_range_index = None
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Cleared ranges for {source.path.name}")

    def _remove_selected_range(self) -> None:
        source = self._current_source()
        if source is None:
            return
        selection = self.range_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index < 0 or index >= len(source.ranges):
            return
        removed = source.ranges.pop(index)
        self._reindex_ranges(source)
        self.selected_range_index = None
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Removed range {removed.index} from {source.path.name}")

    def _add_selected_range_to_batch(self) -> None:
        source = self._current_source()
        preset = self._selected_preset()
        if source is None or preset is None:
            messagebox.showwarning("Missing data", "Please select a source and a preset first.")
            return
        selection = self.range_listbox.curselection()
        if not selection:
            messagebox.showwarning("No range", "Select a range from the source first.")
            return
        index = selection[0]
        if index < 0 or index >= len(source.ranges):
            return
        clip = source.ranges[index]
        jobs = self._build_jobs_for_source(source, preset, [clip])
        self.batch_jobs.extend(jobs)
        self._refresh_jobs_view()
        self._save_session()
        self._log(f"Queued selected range {clip.index} from {source.path.name}.")

    def _add_current_source_to_batch(self) -> None:
        source = self._current_source()
        preset = self._selected_preset()
        if source is None or preset is None:
            messagebox.showwarning("Missing data", "Please select a source and a preset first.")
            return
        if not source.ranges:
            messagebox.showwarning("No ranges", "Add at least one clip range before queueing.")
            return
        jobs = self._build_jobs_for_source(source, preset)
        self.batch_jobs.extend(jobs)
        self._refresh_jobs_view()
        self._save_session()
        self._log(f"Added {len(jobs)} job(s) from {source.path.name}.")

    def _add_all_sources_to_batch(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            messagebox.showwarning("Missing preset", "Please select a preset first.")
            return
        total_added = 0
        for source in self.sources:
            if not source.ranges:
                continue
            jobs = self._build_jobs_for_source(source, preset)
            self.batch_jobs.extend(jobs)
            total_added += len(jobs)
        self._refresh_jobs_view()
        self._save_session()
        self._log(f"Added {total_added} job(s) from all sources.")

    def _clear_queue(self) -> None:
        if self._queue_is_running():
            messagebox.showwarning("Queue running", "Stop encoding before modifying the queue.")
            return
        self.batch_jobs.clear()
        self._refresh_jobs_view()
        self._save_session()
        self._log("Queue cleared.")

    def _remove_selected_jobs(self) -> None:
        if self._queue_is_running():
            messagebox.showwarning("Queue running", "Stop encoding before modifying the queue.")
            return
        selection = self.queue_tree.selection()
        if not selection:
            return
        indices = sorted((self.queue_tree.index(item_id) for item_id in selection), reverse=True)
        removed_count = 0
        for index in indices:
            if 0 <= index < len(self.batch_jobs):
                del self.batch_jobs[index]
                removed_count += 1
        if removed_count == 0:
            return
        self._refresh_jobs_view()
        self._save_session()
        self._log(f"Removed {removed_count} selected job(s) from the queue.")

    def _build_jobs_for_source(self, source: VideoSource, preset: PresetTemplate, clips: list[ClipRange] | None = None) -> list[EncodeJob]:
        output_dir = self.output_dir_var.get().strip()
        target_dir = Path(output_dir) if output_dir else source.path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        jobs: list[EncodeJob] = []
        use_clips = clips if clips is not None else source.ranges
        output_suffix = self._get_output_suffix_for_preset(preset)
        reserved_paths = {job.output_path.resolve() for job in self.batch_jobs}
        for clip in use_clips:
            output_stem = f"{source.stem}-{clip.index}"
            output_path = self._build_unique_output_path(target_dir, output_stem, output_suffix, reserved_paths)
            reserved_paths.add(output_path.resolve())
            jobs.append(
                EncodeJob(
                    source_path=source.path,
                    output_path=output_path,
                    preset_name=preset.name,
                    preset_args=list(preset.handbrake_args),
                    start_frame=clip.start_frame,
                    end_frame=clip.end_frame,
                    display_name=f"{source.path.stem}-{clip.index}",
                )
            )
        return jobs

    def _get_output_suffix_for_preset(self, preset: PresetTemplate) -> str:
        args = preset.handbrake_args
        for index, value in enumerate(args[:-1]):
            if value != "--format":
                continue
            format_name = args[index + 1].strip().lower()
            if format_name == "av_mp4":
                return ".mp4"
            if format_name == "av_mkv":
                return ".mkv"
            if format_name == "av_webm":
                return ".webm"
        return ".mp4"

    def _build_unique_output_path(
        self,
        target_dir: Path,
        output_stem: str,
        output_suffix: str,
        reserved_paths: set[Path],
    ) -> Path:
        candidate = target_dir / f"{output_stem}{output_suffix}"
        if not candidate.exists() and candidate.resolve() not in reserved_paths:
            return candidate

        duplicate_index = 2
        while True:
            candidate = target_dir / f"{output_stem}-{duplicate_index}{output_suffix}"
            if not candidate.exists() and candidate.resolve() not in reserved_paths:
                return candidate
            duplicate_index += 1

    def _start_encoding(self) -> None:
        if not self.batch_jobs:
            messagebox.showinfo("Queue empty", "Add at least one job before encoding.")
            return
        hb_path = Path(self.handbrake_path_var.get().strip())
        if not hb_path.exists():
            messagebox.showerror("HandBrake not found", f"HandBrakeCLI.exe does not exist at:\n{hb_path}")
            return
        runner = HandBrakeRunner(HandBrakeSettings(executable=hb_path))
        self.job_queue = SequentialJobQueue(runner)
        self.job_queue.add_jobs(list(self.batch_jobs))
        self.status_var.set("Encoding")
        self.current_job_var.set("Current job: starting")
        self._log(f"Starting {len(self.batch_jobs)} job(s).")
        self.job_queue.start(self.progress_events.put)

    def _stop_queue(self) -> None:
        if self.job_queue is not None:
            self.job_queue.request_stop()
            self._log("Stop requested.")

    def _queue_is_running(self) -> bool:
        return self.job_queue is not None and self.job_queue.is_running()

    def _refresh_sources_view(self) -> None:
        self.source_listbox.delete(0, tk.END)
        for source in self.sources:
            self.source_listbox.insert(tk.END, source.path.name)
        if self.selected_source_index is not None and self.selected_source_index < len(self.sources):
            self.source_listbox.selection_set(self.selected_source_index)
            self.source_listbox.see(self.selected_source_index)

    def _refresh_ranges_view(self) -> None:
        self.range_listbox.delete(0, tk.END)
        source = self._current_source()
        if source is None:
            self.source_info_var.set("No source selected")
            return
        max_frame_index = source.max_frame_index
        if source.total_frames is not None and max_frame_index is not None:
            self.source_info_var.set(f"Total frames: {source.total_frames} | Valid frame index: 0 - {max_frame_index}")
        elif source.probe_error:
            self.source_info_var.set(f"Frame scan unavailable: {source.probe_error}")
        else:
            self.source_info_var.set("Frame scan pending")
        for clip in source.ranges:
            self.range_listbox.insert(tk.END, f"{clip.index}: frame {clip.start_frame} - {clip.end_frame} ({clip.duration_frames} frames)")
        if self.selected_range_index is not None and self.selected_range_index < len(source.ranges):
            self.range_listbox.selection_set(self.selected_range_index)
            self.range_listbox.see(self.selected_range_index)

    def _refresh_jobs_view(self) -> None:
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        for job in self.batch_jobs:
            self.queue_tree.insert(
                "",
                tk.END,
                values=(job.source_path.name, f"{job.start_frame}-{job.end_frame}", job.output_path.name, job.preset_name),
            )
        self.queue_var.set(f"Queue: {len(self.batch_jobs)} jobs")

    def _poll_progress_events(self) -> None:
        try:
            while True:
                event = self.progress_events.get_nowait()
                self._apply_progress_event(event)
        except queue.Empty:
            pass
        try:
            while True:
                source_path, total_frames, probe_error = self.probe_events.get_nowait()
                self._apply_probe_event(source_path, total_frames, probe_error)
        except queue.Empty:
            pass
        self.after(150, self._poll_progress_events)

    def _apply_progress_event(self, event: JobProgress) -> None:
        if event.current_job:
            self.current_job_var.set(f"Current job: {event.current_job}")
        if event.percent is not None:
            self.progress_var.set(f"{event.percent:.1f}%")
        else:
            self.progress_var.set("0%")
        self.status_var.set(event.status.title())
        if event.total_jobs:
            self.queue_var.set(f"Queue: {event.completed_jobs}/{event.total_jobs}")
        if event.status in {"succeeded", "failed"} and self.batch_jobs:
            self.batch_jobs.pop(0)
            self._save_session()
        if event.message and event.status != "running":
            self._log(event.message)
        if event.status in {"succeeded", "failed", "cancelled", "idle"}:
            self._refresh_jobs_view()

    def _apply_probe_event(self, source_path: str, total_frames: int | None, probe_error: str) -> None:
        for source in self.sources:
            if str(source.path) != source_path:
                continue
            source.total_frames = total_frames
            source.probe_error = probe_error
            if total_frames is not None:
                self._log(f"Scanned {source.path.name}: total frames {total_frames}")
            elif probe_error:
                self._log(f"Frame scan failed for {source.path.name}: {probe_error}")
            self._refresh_ranges_view()
            self._save_session()
            return

    def _log(self, text: str) -> None:
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _create_runner_if_available(self) -> HandBrakeRunner | None:
        hb_path = Path(self.handbrake_path_var.get().strip())
        if not hb_path.exists():
            return None
        return HandBrakeRunner(HandBrakeSettings(executable=hb_path))

    def _probe_source_async(self, source_path: Path, runner: HandBrakeRunner) -> None:
        try:
            total_frames = runner.probe_source(source_path)
            self.probe_events.put((str(source_path), total_frames, ""))
        except Exception as exc:
            self.probe_events.put((str(source_path), None, str(exc)))

    def _load_session(self) -> None:
        payload = self.session_store.load()
        self.sources = self.session_store.restore_sources(payload)
        self.batch_jobs = self.session_store.restore_jobs(payload)
        if self.sources:
            self.selected_source_index = 0

    def _save_session(self) -> None:
        self.session_store.save(self.sources, self.batch_jobs)

    def save_state(self) -> None:
        self.settings["handbrake_path"] = self.handbrake_path_var.get().strip()
        self.settings["default_output_dir"] = self.output_dir_var.get().strip()
        self.settings["last_preset"] = self.preset_var.get().strip()
        self.config_store.save(self.settings)
        self._save_session()
