"""Source editing, clip ranges, and encoding queue mixin.

中文说明：负责来源选择、截取范围编辑、编码队列和编码任务控制。
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from .handbrake_cli import HandBrakeRunner, HandBrakeSettings
from .models import ClipRange, EncodeJob, PresetTemplate, VideoSource
from .queue_service import SequentialJobQueue
from .ui_constants import TIME_CODE_PATTERN


class OperationsMixin:
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
        source = self._current_source()
        if source is not None:
            self._apply_preset_for_source(source)
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
        start_text = self._coerce_frame_var(self.start_frame_var)
        end_text = self._coerce_frame_var(self.end_frame_var)
        if not start_text or not end_text:
            self._update_frame_count_display()
            return
        try:
            start_frame = self._parse_frame_text(start_text)
            end_frame = self._parse_frame_text(end_text)
        except ValueError:
            self._update_frame_count_display()
            return
        if start_frame > end_frame:
            self.end_frame_var.set("")
            self.frame_count_var.set("")
            return
        self._update_frame_count_display()

    def _on_end_frame_changed(self, *_args: object) -> None:
        self._coerce_frame_var(self.end_frame_var)
        self._update_frame_count_display()

    def _update_frame_count_display(self) -> None:
        start_text = self.start_frame_var.get().strip()
        end_text = self.end_frame_var.get().strip()
        if not start_text or not end_text:
            self.frame_count_var.set("")
            return
        try:
            start_frame = self._parse_frame_text(start_text)
            end_frame = self._parse_frame_text(end_text)
        except ValueError:
            self.frame_count_var.set("")
            return
        if end_frame <= start_frame:
            self.frame_count_var.set("")
            return
        self.frame_count_var.set(str(end_frame - start_frame + 1))

    def _normalize_frame_text(self, value: str, audio_only: bool | None = None) -> str:
        text = value.strip()
        if not text:
            return text
        if audio_only is None:
            source = self._current_source()
            audio_only = source is not None and source.is_audio_only
        if audio_only:
            match = TIME_CODE_PATTERN.fullmatch(text)
            if match:
                milliseconds = int(match.group("milliseconds") or "0")
                milliseconds *= 10 ** (3 - len(match.group("milliseconds") or "0"))
                total_milliseconds = (
                    int(match.group("hours")) * 3_600_000
                    + int(match.group("minutes")) * 60_000
                    + int(match.group("seconds")) * 1_000
                    + milliseconds
                )
                return str(total_milliseconds)
        if "," not in text:
            return text
        frame_text, _, _rest = text.partition(",")
        frame_text = frame_text.strip()
        try:
            return str(int(frame_text))
        except ValueError:
            return text

    def _coerce_frame_var(self, variable: tk.StringVar) -> str:
        raw_value = variable.get()
        normalized_value = self._normalize_frame_text(raw_value)
        if normalized_value != raw_value:
            variable.set(normalized_value)
        return normalized_value.strip()

    def _parse_frame_text(self, value: str) -> int:
        return int(self._normalize_frame_text(value))

    def _clear_range_inputs(self) -> None:
        self.start_frame_var.set("")
        self.end_frame_var.set("")
        self.frame_count_var.set("")

    def _fill_full_video_range(self) -> None:
        source = self._current_source()
        if source is None:
            messagebox.showwarning("No source", "Please import and select a video first.")
            return
        max_frame_index = source.max_frame_index
        if max_frame_index is None:
            messagebox.showwarning("Frame scan pending", "Wait for frame scan to finish before filling the full video range.")
            return
        self.start_frame_var.set("0")
        self.end_frame_var.set(str(max_frame_index))

    def _current_source(self) -> VideoSource | None:
        if self.selected_source_index is None:
            return None
        if self.selected_source_index >= len(self.sources):
            return None
        return self.sources[self.selected_source_index]

    def _read_range_inputs(self, source: VideoSource) -> tuple[int, int, int]:
        try:
            start_frame = self._parse_frame_text(self.start_frame_var.get())
            end_frame = self._parse_frame_text(self.end_frame_var.get())
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
        self._refresh_sources_view()
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
        clip.completed = False
        self.selected_range_index = index
        self._refresh_sources_view()
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
        self._refresh_sources_view()
        self._refresh_ranges_view()
        self._save_session()
        self._log(f"Sorted {len(source.ranges)} range(s) for {source.path.name} by start frame.")

    def _clear_ranges(self) -> None:
        source = self._current_source()
        if source is None:
            return
        source.ranges.clear()
        self.selected_range_index = None
        self._refresh_sources_view()
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
        self._refresh_sources_view()
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
                    clip_index=clip.index,
                    preset_name=preset.name,
                    preset_args=list(preset.handbrake_args),
                    start_frame=clip.start_frame,
                    end_frame=clip.end_frame,
                    display_name=f"{source.path.stem}-{clip.index}",
                    preset_mode=preset.mode,
                    source_frame_rate=source.frame_rate,
                    source_is_audio_only=source.is_audio_only,
                )
            )
        return jobs

    def _get_output_suffix_for_preset(self, preset: PresetTemplate) -> str:
        if preset.mode == "audio_copy":
            return ".mka"
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
        ffmpeg_text = self.ffmpeg_path_var.get().strip()
        ffmpeg_path = Path(ffmpeg_text) if ffmpeg_text else None
        needs_handbrake = any(job.preset_mode != "audio_copy" for job in self.batch_jobs)
        needs_ffmpeg = any(job.preset_mode == "audio_copy" for job in self.batch_jobs)
        if needs_handbrake and not hb_path.exists():
            messagebox.showerror("HandBrake not found", f"HandBrakeCLI.exe does not exist at:\n{hb_path}")
            return
        if needs_ffmpeg and ffmpeg_path is not None and not ffmpeg_path.exists():
            messagebox.showerror("FFmpeg not found", f"ffmpeg.exe does not exist at:\n{ffmpeg_path}")
            return
        runner = HandBrakeRunner(HandBrakeSettings(executable=hb_path, ffmpeg_executable=ffmpeg_path))
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
