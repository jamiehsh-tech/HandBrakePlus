"""Source import and media merge mixin.

中文说明：负责视频/音频导入、拖放处理、合并列表和媒体合并任务。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .handbrake_cli import HandBrakeRunner, HandBrakeSettings
from .ui_constants import MIN_FOLDER_IMPORT_SIZE_BYTES, VIDEO_EXTENSIONS


class MediaMixin:
    def _add_videos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select source videos",
            filetypes=(("Video/audio files", "*.mp4 *.mkv *.mov *.avi *.wmv *.ts *.m4v *.mka"), ("All files", "*.*")),
        )
        self._import_video_paths(paths)

    def _add_merge_files(self, paths: tuple[str, ...] | list[str] | None = None) -> None:
        if paths is None:
            paths = filedialog.askopenfilenames(
                title="Select files to merge",
                filetypes=(("Video/audio files", "*.mp4 *.mkv *.mov *.avi *.wmv *.ts *.m4v *.mka"), ("All files", "*.*")),
            )
        if not paths:
            return

        candidates = self._iter_import_candidates(paths, expand_directories=False)
        if not candidates:
            messagebox.showwarning("Merge mode", "Select at least one supported video or audio file.")
            return

        existing_extensions = {path.suffix.lower() for path in self.merge_input_paths}
        candidate_extensions = {path.suffix.lower() for path in candidates}
        if len(existing_extensions | candidate_extensions) > 1:
            messagebox.showerror("Merge failed", "All files in merge mode must have the same file type.")
            return

        existing_paths = {path.resolve() for path in self.merge_input_paths}
        added_count = 0
        for path in candidates:
            resolved_path = path.resolve()
            if resolved_path in existing_paths:
                continue
            self.merge_input_paths.append(resolved_path)
            existing_paths.add(resolved_path)
            added_count += 1
        self._refresh_merge_view()
        if added_count:
            self._log(f"Added {added_count} file(s) to merge list.")

    def _on_merge_files_dropped(self, event: object) -> None:
        raw_data = getattr(event, "data", "")
        if not raw_data:
            return
        try:
            paths = list(self.tk.splitlist(raw_data))
        except tk.TclError:
            paths = []
        if not paths:
            paths = [raw_data]
        self._add_merge_files(paths)

    def _refresh_merge_view(self, selected_indices: list[int] | None = None) -> None:
        self.merge_listbox.delete(0, tk.END)
        for path in self.merge_input_paths:
            label = str(path)
            if path.resolve() in self.merge_completed_paths:
                label += " [OK]"
            self.merge_listbox.insert(tk.END, label)
        if selected_indices:
            valid_indices = [index for index in selected_indices if 0 <= index < len(self.merge_input_paths)]
            for index in valid_indices:
                self.merge_listbox.selection_set(index)
            if valid_indices:
                self.merge_listbox.see(valid_indices[0])

    def _move_merge_up(self) -> None:
        selected = sorted(self.merge_listbox.curselection())
        if not selected or selected[0] == 0:
            return
        selected_set = set(selected)
        for index in selected:
            if index - 1 not in selected_set:
                self.merge_input_paths[index - 1], self.merge_input_paths[index] = (
                    self.merge_input_paths[index],
                    self.merge_input_paths[index - 1],
                )
        self._refresh_merge_view([index - 1 if index > 0 else index for index in selected])

    def _move_merge_down(self) -> None:
        selected = sorted(self.merge_listbox.curselection())
        if not selected or selected[-1] >= len(self.merge_input_paths) - 1:
            return
        selected_set = set(selected)
        for index in reversed(selected):
            if index + 1 not in selected_set:
                self.merge_input_paths[index + 1], self.merge_input_paths[index] = (
                    self.merge_input_paths[index],
                    self.merge_input_paths[index + 1],
                )
        self._refresh_merge_view([index + 1 if index < len(self.merge_input_paths) - 1 else index for index in selected])

    def _remove_merge_files(self) -> None:
        selected = sorted(self.merge_listbox.curselection(), reverse=True)
        if not selected:
            return
        for index in selected:
            if 0 <= index < len(self.merge_input_paths):
                del self.merge_input_paths[index]
        self._refresh_merge_view()

    def _clear_merge_files(self) -> None:
        if not self.merge_input_paths:
            return
        self.merge_input_paths.clear()
        self._refresh_merge_view()

    def _merge_selected_files(self) -> None:
        self._start_merge(list(self.merge_input_paths))

    def _start_merge(self, input_paths: list[Path]) -> None:
        unique_paths = list(dict.fromkeys(path.resolve() for path in input_paths if path.is_file()))
        if len(unique_paths) < 2:
            messagebox.showwarning("Merge mode", "Select or drop at least two files to merge.")
            return
        extensions = {path.suffix.lower() for path in unique_paths}
        if len(extensions) != 1:
            messagebox.showerror("Merge failed", "All files must have the same file type before merging.")
            return
        suffix = next(iter(extensions))
        output_path = unique_paths[0].parent / f"{unique_paths[0].stem}-merge{suffix}"
        if output_path.resolve() in unique_paths:
            messagebox.showerror("Merge failed", "The output file cannot be one of the input files.")
            return
        if output_path.exists() and not messagebox.askyesno("Overwrite merged file", f"{output_path.name} already exists. Overwrite it?"):
            return
        self.merge_completed_paths.difference_update(unique_paths)
        self.merge_completed_paths.discard(output_path.resolve())
        self.merge_pending_paths = list(unique_paths)
        self._refresh_merge_view()
        self._log(f"Merging {len(unique_paths)} {suffix} file(s)...")
        threading.Thread(
            target=self._merge_files_async,
            args=(unique_paths, output_path),
            daemon=True,
        ).start()

    def _merge_files_async(self, input_paths: list[Path], output_path: Path) -> None:
        hb_path = Path(self.handbrake_path_var.get().strip())
        ffmpeg_text = self.ffmpeg_path_var.get().strip()
        ffmpeg_path = Path(ffmpeg_text) if ffmpeg_text else None
        runner = HandBrakeRunner(HandBrakeSettings(executable=hb_path, ffmpeg_executable=ffmpeg_path))
        try:
            runner.merge_files(input_paths, output_path)
        except Exception as exc:
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            report_lines = [
                "HandBrakePlus merge failed",
                f"Output: {output_path}",
                "Inputs:",
                *(f"  {path}" for path in input_paths),
                "",
                str(exc),
            ]
            self.merge_events.put((None, "\n".join(report_lines)))
            return
        self.merge_events.put((output_path, ""))

    def _show_copyable_error(self, title: str, message: str) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("780x460")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        error_text = tk.Text(dialog, wrap="word")
        error_text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=error_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        error_text.configure(yscrollcommand=scrollbar.set)
        error_text.insert("1.0", message)
        error_text.configure(state="disabled")

        button_bar = ttk.Frame(dialog)
        button_bar.grid(row=1, column=0, columnspan=2, sticky="e", padx=12, pady=(0, 12))

        def copy_error() -> None:

            self.clipboard_clear()
            self.clipboard_append(message)
            self.update()
            copy_button.configure(text="Copied")

        copy_button = ttk.Button(button_bar, text="Copy error", command=copy_error)
        copy_button.pack(side="left", padx=(0, 8))
        ttk.Button(button_bar, text="Close", command=dialog.destroy).pack(side="left")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

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
        source = self._current_source()
        if source is not None:
            self._apply_preset_for_source(source)
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

    def _import_video_paths(
        self,
        paths: tuple[str, ...] | list[str],
        expand_directories: bool = False,
    ) -> None:
        if not paths:
            return
        candidate_paths = self._iter_import_candidates(paths, expand_directories=expand_directories)
        existing = {source.path for source in self.sources}
        added_count = 0
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
        source = self._current_source()
        if source is not None:
            self._apply_preset_for_source(source)
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
