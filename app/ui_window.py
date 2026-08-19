"""Window layout, view modes, and preset editor mixin.

中文说明：负责窗口布局、View 模式切换、配置控件和预设编辑窗口。
"""

from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from .models import PresetTemplate, VideoSource
from .ui_constants import (
    COMPACT_MIN_WINDOW_SIZE,
    COMPACT_WINDOW_SIZE,
    FULL_VIEW_MODE,
    IMPORT_ONLY_VIEW_MODE,
    LEFT_ONLY_MIN_WINDOW_SIZE,
    LEFT_ONLY_VIEW_MODE,
    LEFT_ONLY_WINDOW_SIZE,
    MERGE_MIN_WINDOW_SIZE,
    MERGE_VIEW_MODE,
    MERGE_WINDOW_SIZE,
    NORMAL_MIN_WINDOW_SIZE,
    VALID_VIEW_MODES,
)
from .ui_sections import MergeSection, ProgressSection, QueueSection, RangeSection, SourceSection
from .ui_support import DND_FILES, TkinterDnD


class WindowMixin:
    def _resource_root(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return Path(__file__).resolve().parent.parent

    def _storage_root(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
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
        self.rowconfigure(2, weight=1)

        self._build_view_menu()

        self.config_frame = ttk.LabelFrame(self, text="Config")
        self.config_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self.config_frame.columnconfigure(1, weight=1)
        self.config_frame.columnconfigure(4, weight=1)
        self.config_frame.columnconfigure(5, weight=1)

        ttk.Label(self.config_frame, text="HandBrakeCLI").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.config_frame, textvariable=self.handbrake_path_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        ttk.Button(self.config_frame, text="Browse", command=self._browse_handbrake).grid(row=0, column=4, sticky="ew", padx=8, pady=6)

        ttk.Label(self.config_frame, text="FFmpeg (audio preset)").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.config_frame, textvariable=self.ffmpeg_path_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        ttk.Button(self.config_frame, text="Browse", command=self._browse_ffmpeg).grid(row=1, column=4, sticky="ew", padx=8, pady=6)

        ttk.Label(self.config_frame, text="Output folder").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.config_frame, textvariable=self.output_dir_var).grid(row=2, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        ttk.Button(self.config_frame, text="Browse", command=self._browse_output_dir).grid(row=2, column=4, sticky="ew", padx=8, pady=6)

        ttk.Label(self.config_frame, text="Preset").grid(row=3, column=0, sticky="w", padx=8, pady=6)
        preset_values = [preset.name for preset in self.presets]
        self.preset_combo = ttk.Combobox(self.config_frame, textvariable=self.preset_var, values=preset_values, state="readonly")
        self.preset_combo.grid(row=3, column=1, sticky="ew", padx=8, pady=6)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_preset_changed())
        ttk.Button(self.config_frame, text="Edit presets", command=self._open_preset_editor).grid(row=3, column=2, sticky="w", padx=8, pady=6)
        ttk.Label(self.config_frame, textvariable=self.status_var).grid(row=3, column=3, columnspan=3, sticky="w", padx=8, pady=6)

        self.main_frame = ttk.Frame(self)
        self.main_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=0)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

        self.left_panel = ttk.Frame(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.left_panel.rowconfigure(0, weight=0)
        self.left_panel.rowconfigure(1, weight=2)
        self.left_panel.columnconfigure(0, weight=1)

        self.source_frame = SourceSection(self.left_panel).build(self)
        self.source_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._register_source_drop_targets()
        self.range_frame = RangeSection(self.left_panel).build(self)
        self.range_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        self.right_panel = ttk.Frame(self.main_frame)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.right_panel.rowconfigure(0, weight=2)
        self.right_panel.rowconfigure(1, weight=0)
        self.right_panel.rowconfigure(2, weight=1)
        self.right_panel.columnconfigure(0, weight=1)

        self.queue_frame = QueueSection(self.right_panel).build(self)
        self.queue_frame.grid(row=0, column=0, sticky="nsew")

        self.progress_frame, self.log_frame = ProgressSection(self.right_panel).build(self)
        self.progress_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.log_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

        self.merge_frame = MergeSection(self).build(self)
        self.merge_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=0)
        self._register_merge_drop_targets()

        self._apply_view_mode(self.view_mode_var.get(), restore_geometry=False)

    def _build_view_menu(self) -> None:
        self.view_menu_frame = ttk.Frame(self)
        self.view_menu_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))
        self.view_menu_frame.columnconfigure(4, weight=1)

        ttk.Label(self.view_menu_frame, text="View").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Radiobutton(
            self.view_menu_frame,
            text="Compact mode",
            value=IMPORT_ONLY_VIEW_MODE,
            variable=self.view_mode_var,
            command=lambda: self._set_view_mode(IMPORT_ONLY_VIEW_MODE),
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Radiobutton(
            self.view_menu_frame,
            text="Compact mode 2",
            value=LEFT_ONLY_VIEW_MODE,
            variable=self.view_mode_var,
            command=lambda: self._set_view_mode(LEFT_ONLY_VIEW_MODE),
        ).grid(row=0, column=2, sticky="w", padx=(0, 10))
        ttk.Radiobutton(
            self.view_menu_frame,
            text="Full mode",
            value=FULL_VIEW_MODE,
            variable=self.view_mode_var,
            command=lambda: self._set_view_mode(FULL_VIEW_MODE),
        ).grid(row=0, column=3, sticky="w")
        ttk.Radiobutton(
            self.view_menu_frame,
            text="Merge mode",
            value=MERGE_VIEW_MODE,
            variable=self.view_mode_var,
            command=lambda: self._set_view_mode(MERGE_VIEW_MODE),
        ).grid(row=0, column=4, sticky="w", padx=(10, 0))

    def _register_source_drop_targets(self) -> None:
        if TkinterDnD is None or DND_FILES is None:
            return

        def register(widget: tk.Misc) -> None:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_files_dropped)
            for child in widget.winfo_children():
                register(child)

        register(self.source_frame)

    def _register_merge_drop_targets(self) -> None:
        if TkinterDnD is None or DND_FILES is None:
            return

        def register(widget: tk.Misc) -> None:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_merge_files_dropped)
            for child in widget.winfo_children():
                register(child)

        register(self.merge_frame)

    def _set_view_mode(self, mode: str) -> None:
        self.view_mode_var.set(mode)
        self._apply_view_mode(mode)

    def _apply_view_mode(self, mode: str, restore_geometry: bool = True) -> None:
        if mode not in VALID_VIEW_MODES:
            return

        self.update_idletasks()
        previous_mode = self.current_view_mode
        compact_modes = {IMPORT_ONLY_VIEW_MODE, LEFT_ONLY_VIEW_MODE, MERGE_VIEW_MODE}
        entering_compact = previous_mode == FULL_VIEW_MODE and mode in compact_modes
        leaving_compact = previous_mode in compact_modes and mode == FULL_VIEW_MODE

        if entering_compact:
            self._pre_compact_geometry = self.geometry()
            self._pre_compact_window_state = self.state()
            if self._pre_compact_window_state == "zoomed":
                self.state("normal")
        elif mode != FULL_VIEW_MODE and self.state() == "zoomed":
            self.state("normal")

        self.config_frame.grid()
        self.main_frame.grid()
        self.merge_frame.grid_remove()
        self.range_frame.grid()
        self.right_panel.grid()
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.left_panel.rowconfigure(0, weight=0)
        self.left_panel.rowconfigure(1, weight=2)
        self.left_panel.grid_configure(padx=(0, 8))
        self.source_frame.grid_configure(pady=(0, 8))

        if mode == IMPORT_ONLY_VIEW_MODE:
            self.config_frame.grid_remove()
            self.range_frame.grid_remove()
            self.right_panel.grid_remove()
            self.main_frame.columnconfigure(1, weight=0)
            self.left_panel.rowconfigure(0, weight=1)
            self.left_panel.rowconfigure(1, weight=0)
            self.left_panel.grid_configure(padx=0)
            self.source_frame.grid_configure(pady=0)
            self.minsize(*COMPACT_MIN_WINDOW_SIZE)
            if restore_geometry:
                self.geometry(f"{COMPACT_WINDOW_SIZE[0]}x{COMPACT_WINDOW_SIZE[1]}")
        elif mode == LEFT_ONLY_VIEW_MODE:
            self.right_panel.grid_remove()
            self.main_frame.columnconfigure(1, weight=0)
            self.left_panel.grid_configure(padx=0)
            self.minsize(*LEFT_ONLY_MIN_WINDOW_SIZE)
            if restore_geometry:
                self.geometry(f"{LEFT_ONLY_WINDOW_SIZE[0]}x{LEFT_ONLY_WINDOW_SIZE[1]}")
        elif mode == MERGE_VIEW_MODE:
            self.config_frame.grid_remove()
            self.main_frame.grid_remove()
            self.merge_frame.grid()
            self.minsize(*MERGE_MIN_WINDOW_SIZE)
            if restore_geometry:
                self.geometry(f"{MERGE_WINDOW_SIZE[0]}x{MERGE_WINDOW_SIZE[1]}")
        else:
            self.minsize(*NORMAL_MIN_WINDOW_SIZE)
            if leaving_compact:
                if self._pre_compact_window_state == "zoomed":
                    self.state("zoomed")
                elif self._pre_compact_geometry:
                    self.geometry(self._pre_compact_geometry)

        self.current_view_mode = mode

    def _browse_handbrake(self) -> None:
        path = filedialog.askopenfilename(title="Select HandBrakeCLI.exe", filetypes=(("Executable", "*.exe"), ("All files", "*.*")))
        if path:
            self.handbrake_path_var.set(path)

    def _browse_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(title="Select ffmpeg.exe", filetypes=(("Executable", "*.exe"), ("All files", "*.*")))
        if path:
            self.ffmpeg_path_var.set(path)

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
                "mode": preset.mode,
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
        editor_frame.rowconfigure(3, weight=1)

        name_var = tk.StringVar()
        description_var = tk.StringVar()
        mode_var = tk.StringVar(value="handbrake")

        ttk.Label(editor_frame, text="Name").grid(row=0, column=0, sticky="w", pady=(0, 8))
        name_entry = ttk.Entry(editor_frame, textvariable=name_var)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(editor_frame, text="Description").grid(row=1, column=0, sticky="w", pady=(0, 8))
        description_entry = ttk.Entry(editor_frame, textvariable=description_var)
        description_entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(editor_frame, text="Mode").grid(row=2, column=0, sticky="w", pady=(0, 8))
        mode_combo = ttk.Combobox(editor_frame, textvariable=mode_var, values=("handbrake", "audio_copy"), state="readonly")
        mode_combo.grid(row=2, column=1, sticky="w", pady=(0, 8))

        ttk.Label(editor_frame, text="HandBrake args").grid(row=3, column=0, sticky="nw", pady=(0, 8))
        args_text = tk.Text(editor_frame, height=18, wrap="word")
        args_text.grid(row=3, column=1, sticky="nsew", pady=(0, 8))

        ttk.Label(
            editor_frame,
            text="One argument per line, or paste space-separated arguments. Example: --encoder nvenc_h265",
        ).grid(row=4, column=1, sticky="w", pady=(0, 8))

        button_bar = ttk.Frame(editor_frame)
        button_bar.grid(row=5, column=1, sticky="w", pady=(0, 8))

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
                mode_var.set("handbrake")
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
            mode_var.set(item.get("mode", "handbrake"))
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
                "mode": mode_var.get().strip() or "handbrake",
            }
            refresh_preset_list(index)

        def add_preset() -> None:
            preset_items.append({"name": "New preset", "description": "", "handbrake_args": [], "mode": "handbrake"})
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
                        "mode": str(item.get("mode", "handbrake")).strip() or "handbrake",
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

    def _find_preset_by_keyword(self, keyword: str) -> PresetTemplate | None:
        keyword_lower = keyword.lower()
        for preset in self.presets:
            if keyword_lower in preset.name.lower():
                return preset
        return None

    def _recommended_preset_for_source(self, source: VideoSource) -> PresetTemplate | None:
        if source.is_audio_only:
            for preset in self.presets:
                if preset.mode == "audio_copy":
                    return preset
        fallback = self._find_preset_by_keyword("1080")
        if fallback is None:
            fallback = self.presets[0] if self.presets else None
        width = source.width
        height = source.height
        if width is None or height is None:
            return fallback
        if width >= 3840 or height >= 2160:
            return self._find_preset_by_keyword("4k") or fallback
        if width >= 1920 or height >= 1080:
            return self._find_preset_by_keyword("1080") or fallback
        if width >= 1280 or height >= 720:
            return self._find_preset_by_keyword("720") or fallback
        return fallback

    def _apply_preset_for_source(self, source: VideoSource) -> None:
        preset = self._recommended_preset_for_source(source)
        if preset is None or self.preset_var.get() == preset.name:
            return
        self.preset_var.set(preset.name)
        self._on_preset_changed()

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
