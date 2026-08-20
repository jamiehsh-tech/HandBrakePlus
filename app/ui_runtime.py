"""Runtime events, progress, probing, and session mixin.

中文说明：负责进度事件、媒体扫描、运行日志、Session 保存和运行时状态更新。
"""

from __future__ import annotations

import queue
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from .handbrake_cli import HandBrakeRunner, HandBrakeSettings, SourceScanResult
from .models import EncodeJob, JobProgress
from .ui_constants import FULL_VIEW_MODE


class RuntimeMixin:
    def _refresh_sources_view(self) -> None:
        self.source_listbox.delete(0, tk.END)
        for source in self.sources:
            source_label = source.path.name
            if (source.ranges and all(clip.completed for clip in source.ranges)) or source.path.resolve() in self.merge_completed_paths:
                source_label += " [OK]"
            self.source_listbox.insert(tk.END, source_label)
        if self.selected_source_index is not None and self.selected_source_index < len(self.sources):
            self.source_listbox.selection_set(self.selected_source_index)
            self.source_listbox.see(self.selected_source_index)

    def _refresh_ranges_view(self) -> None:
        self.range_listbox.delete(0, tk.END)
        source = self._current_source()
        if source is None:
            self.source_info_var.set("No source selected")
            self._clear_range_inputs()
            return
        max_frame_index = source.max_frame_index
        if source.total_frames is not None and max_frame_index is not None:
            if source.is_audio_only:
                duration_text = f" | Duration: {source.duration_seconds:.3f}s" if source.duration_seconds is not None else ""
                self.source_info_var.set(
                    f"Audio timeline: milliseconds (timecode paste supported)\n"
                    f"Valid range: 0 - {max_frame_index}{duration_text}"
                )
            else:
                self.source_info_var.set(f"Total frames: {source.total_frames} | Valid frame index: 0 - {max_frame_index}")
        elif source.probe_error:
            self.source_info_var.set(f"Frame scan unavailable: {source.probe_error}")
        else:
            self.source_info_var.set("Frame scan pending")
        for clip in source.ranges:
            unit = "ms" if source.is_audio_only else "frame"
            duration_unit = "ms" if source.is_audio_only else "frames"
            clip_label = f"{clip.index}: {unit} {clip.start_frame} - {clip.end_frame} ({clip.duration_frames} {duration_unit})"
            if clip.completed:
                clip_label += " [OK]"
            self.range_listbox.insert(tk.END, clip_label)
        if self.selected_range_index is not None and self.selected_range_index < len(source.ranges):
            self.range_listbox.selection_set(self.selected_range_index)
            self.range_listbox.see(self.selected_range_index)
        else:
            self._clear_range_inputs()

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
                source_path, scan_result, probe_error = self.probe_events.get_nowait()
                self._apply_probe_event(source_path, scan_result, probe_error)
        except queue.Empty:
            pass
        try:
            while True:
                merged_path, merge_error = self.merge_events.get_nowait()
                if merge_error:
                    self.merge_pending_paths.clear()
                    self._log(f"Merge failed: {merge_error}")
                    self._show_copyable_error("Merge failed", merge_error)
                elif merged_path is not None:
                    self._log(f"Merged file created: {merged_path.name}")
                    completed_inputs = self.merge_pending_paths or self.merge_input_paths
                    self.merge_completed_paths.update(path.resolve() for path in completed_inputs)
                    self.merge_completed_paths.add(merged_path.resolve())
                    self.merge_pending_paths.clear()
                    self._refresh_merge_view()
                    self._refresh_sources_view()
                    messagebox.showinfo("Merge completed", f"Merged file created:\n{merged_path}")
                    self._import_video_paths([str(merged_path)])
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
        if event.status == "succeeded":
            self._mark_job_completed(event)
        if event.status in {"succeeded", "failed"} and self.batch_jobs:
            self.batch_jobs.pop(0)
            self._save_session()
        if event.message and event.status != "running":
            self._log(event.message)
        if event.status in {"succeeded", "failed", "cancelled", "idle"}:
            self._refresh_jobs_view()

    def _mark_job_completed(self, event: JobProgress) -> None:
        job = event.extra.get("job")
        if not isinstance(job, EncodeJob):
            return
        for source in self.sources:
            if source.path != job.source_path:
                continue
            for clip in source.ranges:
                if clip.index != job.clip_index:
                    continue
                clip.completed = True
                self._refresh_sources_view()
                if self._current_source() is source:
                    self._refresh_ranges_view()
                return

    def _apply_probe_event(
        self,
        source_path: str,
        scan_result: SourceScanResult | None,
        probe_error: str,
    ) -> None:
        for source in self.sources:
            if str(source.path) != source_path:
                continue
            source.total_frames = scan_result.total_frames if scan_result is not None else None
            source.width = scan_result.width if scan_result is not None else None
            source.height = scan_result.height if scan_result is not None else None
            source.frame_rate = scan_result.frame_rate if scan_result is not None else None
            source.duration_seconds = scan_result.duration_seconds if scan_result is not None else None
            source.is_audio_only = scan_result.is_audio_only if scan_result is not None else False
            source.probe_error = probe_error
            if scan_result is not None:
                if scan_result.is_audio_only:
                    duration_text = f", duration {scan_result.duration_seconds:.3f}s" if scan_result.duration_seconds is not None else ""
                    self._log(f"Scanned audio source {source.path.name}: millisecond timeline{duration_text}")
                else:
                    resolution_text = f", resolution {scan_result.width}x{scan_result.height}" if scan_result.width is not None and scan_result.height is not None else ""
                    self._log(f"Scanned {source.path.name}: total frames {scan_result.total_frames}{resolution_text}")
                if self._current_source() is source:
                    self._apply_preset_for_source(source)
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
        ffmpeg_text = self.ffmpeg_path_var.get().strip()
        ffmpeg_path = Path(ffmpeg_text) if ffmpeg_text else None
        if not hb_path.exists() and (ffmpeg_path is None or not ffmpeg_path.exists()) and not shutil.which("ffmpeg"):
            return None
        return HandBrakeRunner(HandBrakeSettings(executable=hb_path, ffmpeg_executable=ffmpeg_path))

    def _probe_source_async(self, source_path: Path, runner: HandBrakeRunner) -> None:
        try:
            scan_result = runner.probe_source(source_path)
            self.probe_events.put((str(source_path), scan_result, ""))
        except Exception as exc:
            self.probe_events.put((str(source_path), None, str(exc)))

    def _load_session(self) -> None:
        payload = self.session_store.load()
        self.sources = self.session_store.restore_sources(payload)
        self.batch_jobs = self.session_store.restore_jobs(payload)
        if self.sources:
            self.selected_source_index = 0
            self._apply_preset_for_source(self.sources[0])

    def _save_session(self) -> None:
        self.session_store.save(self.sources, self.batch_jobs)

    def save_state(self) -> None:

        self.settings["handbrake_path"] = self.handbrake_path_var.get().strip()
        self.settings["ffmpeg_path"] = self.ffmpeg_path_var.get().strip()
        self.settings["default_output_dir"] = self.output_dir_var.get().strip()
        self.settings["last_preset"] = self.preset_var.get().strip()
        self.settings["last_view_mode"] = self.view_mode_var.get().strip()
        self.config_store.save(self.settings)
        self._save_session()
