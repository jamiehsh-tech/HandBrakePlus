"""HandBrakeCLI command construction and execution helpers."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import EncodeJob, JobProgress


PROGRESS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass(slots=True)
class HandBrakeSettings:
    """Runtime settings for the HandBrake executable."""

    executable: Path
    ffmpeg_executable: Path | None = None


@dataclass(slots=True)
class SourceScanResult:
    """Metadata discovered from a HandBrakeCLI scan."""

    total_frames: int
    width: int | None = None
    height: int | None = None


class StopRequestedError(RuntimeError):
    """Raised when an active HandBrake process is cancelled by the user."""


class HandBrakeRunner:
    """Run HandBrakeCLI jobs sequentially and report progress."""

    def __init__(self, settings: HandBrakeSettings) -> None:
        self.settings = settings
        self._process_lock = threading.Lock()
        self._current_process: subprocess.Popen[str] | None = None
        self._stop_requested = threading.Event()

    def build_command(self, job: EncodeJob) -> list[str]:
        frame_duration = max(1, job.end_frame - job.start_frame + 1)
        command = [
            str(self.settings.executable),
            "-i",
            str(job.source_path),
            "-o",
            str(job.output_path),
            "--start-at",
            f"frame:{job.start_frame}",
            "--stop-at",
            f"frame:{frame_duration}",
        ]
        command.extend(job.preset_args)
        return command

    def build_audio_command(self, job: EncodeJob, frame_rate: float | None = None) -> list[str]:
        """Build an FFmpeg command that copies all audio streams without video."""
        ffmpeg = self._get_ffmpeg_executable()
        rate = frame_rate if frame_rate is not None else self._probe_frame_rate(job.source_path)
        start_seconds = job.start_frame / rate
        duration_seconds = max(1, job.end_frame - job.start_frame + 1) / rate
        return [
            str(ffmpeg),
            "-hide_banner",
            "-y",
            "-ss",
            f"{start_seconds:.6f}",
            "-i",
            str(job.source_path),
            "-map",
            "0:a",
            "-vn",
            "-c:a",
            "copy",
            "-map_metadata",
            "0",
            "-avoid_negative_ts",
            "make_zero",
            "-t",
            f"{duration_seconds:.6f}",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            str(job.output_path),
        ]

    def request_stop(self) -> None:
        self._stop_requested.set()
        with self._process_lock:
            if self._current_process is not None and self._current_process.poll() is None:
                self._current_process.kill()

    def probe_source(self, source_path: Path) -> SourceScanResult:
        command = [
            str(self.settings.executable),
            "-i",
            str(source_path),
            "--scan",
            "--json",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        if completed.returncode != 0:
            raise RuntimeError(output.strip() or f"HandBrakeCLI scan failed with code {completed.returncode}")
        payload = self._extract_scan_json(output)
        titles = payload.get("TitleList") or []
        if not titles:
            raise RuntimeError("HandBrakeCLI scan did not return any titles")
        title = titles[0]
        frame_count = self._extract_frame_count(title)
        if not isinstance(frame_count, int) or frame_count <= 0:
            raise RuntimeError("Unable to determine total frames from HandBrakeCLI scan")
        width, height = self._extract_geometry(title)
        return SourceScanResult(total_frames=frame_count, width=width, height=height)

    def run_job(
        self,
        job: EncodeJob,
        progress_callback: Callable[[JobProgress], None] | None = None,
    ) -> None:
        is_audio_copy = job.preset_mode == "audio_copy"
        frame_rate = self._probe_frame_rate(job.source_path) if is_audio_copy else None
        command = self.build_audio_command(job, frame_rate) if is_audio_copy else self.build_command(job)
        clip_duration = self._get_clip_duration(job, frame_rate) if is_audio_copy else None
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        with self._process_lock:
            self._current_process = process
        try:
            if progress_callback:
                progress_callback(
                    JobProgress(
                        status="running",
                        message="starting",
                        current_job=job.display_name,
                        extra={"job": job},
                    )
                )
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                percent = self._parse_progress(line, clip_duration)
                if progress_callback:
                    progress_callback(
                        JobProgress(
                            status="running",
                            message=line,
                            percent=percent,
                            current_job=job.display_name,
                            extra={"job": job},
                        )
                    )
            return_code = process.wait()
            if return_code != 0:
                if self._stop_requested.is_set():
                    raise StopRequestedError("queue stopped")
                tool_name = "FFmpeg" if is_audio_copy else "HandBrakeCLI"
                raise RuntimeError(f"{tool_name} exited with code {return_code}")
            if progress_callback:
                progress_callback(
                    JobProgress(
                        status="succeeded",
                        message="completed",
                        current_job=job.display_name,
                        extra={"job": job},
                    )
                )
        except Exception:
            if process.poll() is None:
                process.kill()
            raise
        finally:
            with self._process_lock:
                self._current_process = None

    def _parse_percent(self, line: str) -> float | None:
        match = PROGRESS_PATTERN.search(line)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _parse_progress(self, line: str, duration_seconds: float | None) -> float | None:
        if duration_seconds is not None:
            if line == "progress=end":
                return 100.0
            if line.startswith("out_time_us="):
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    return None
                return min(100.0, max(0.0, elapsed / duration_seconds * 100.0))
        return self._parse_percent(line)

    def _get_ffmpeg_executable(self) -> Path:
        configured = self.settings.ffmpeg_executable
        if configured is not None:
            if configured.exists():
                return configured
            raise RuntimeError(f"FFmpeg executable does not exist at:\n{configured}")
        located = shutil.which("ffmpeg")
        if located:
            return Path(located)
        raise RuntimeError("FFmpeg was not found. Set its path in the Config section before using the audio preset.")

    def _get_ffprobe_executable(self) -> Path:
        configured_ffmpeg = self.settings.ffmpeg_executable
        if configured_ffmpeg is not None:
            sibling = configured_ffmpeg.with_name("ffprobe.exe")
            if sibling.exists():
                return sibling
        located = shutil.which("ffprobe")
        if located:
            return Path(located)
        raise RuntimeError("FFprobe was not found. It is required to convert frame ranges to audio time ranges.")

    def _probe_frame_rate(self, source_path: Path) -> float:
        completed = subprocess.run(
            [
                str(self._get_ffprobe_executable()),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        value = completed.stdout.strip()
        if completed.returncode != 0 or not value:
            detail = completed.stderr.strip() or "unable to read video frame rate"
            raise RuntimeError(f"FFprobe failed for {source_path.name}: {detail}")
        try:
            if "/" in value:
                numerator, denominator = value.split("/", 1)
                frame_rate = float(numerator) / float(denominator)
            else:
                frame_rate = float(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise RuntimeError(f"Invalid video frame rate reported for {source_path.name}: {value}") from exc
        if not math.isfinite(frame_rate) or frame_rate <= 0:
            raise RuntimeError(f"Invalid video frame rate reported for {source_path.name}: {value}")
        return frame_rate

    @staticmethod
    def _get_clip_duration(job: EncodeJob, frame_rate: float | None) -> float | None:
        if frame_rate is None:
            return None
        return max(1, job.end_frame - job.start_frame + 1) / frame_rate

    def _extract_scan_json(self, output: str) -> dict:
        decoder = json.JSONDecoder()
        fallback_payload: dict | None = None
        for index, char in enumerate(output):
            if char != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(output[index:])
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if isinstance(payload.get("TitleList"), list):
                return payload
            if fallback_payload is None:
                fallback_payload = payload
        if fallback_payload is not None:
            return fallback_payload
        raise RuntimeError("HandBrakeCLI scan JSON could not be decoded")

    def _extract_frame_count(self, title: dict) -> int | None:
        frame_count = title.get("FrameCount")
        if isinstance(frame_count, int) and frame_count > 0:
            return frame_count

        frame_rate = title.get("FrameRate") or {}
        duration = title.get("Duration") or {}
        if not isinstance(frame_rate, dict) or not isinstance(duration, dict):
            return None

        frame_rate_num = frame_rate.get("Num")
        frame_rate_den = frame_rate.get("Den")
        ticks = duration.get("Ticks")
        if not all(isinstance(value, int) and value > 0 for value in (frame_rate_num, frame_rate_den, ticks)):
            return None

        duration_seconds = ticks / 90000
        computed = duration_seconds * frame_rate_num / frame_rate_den
        if computed <= 0:
            return None
        return max(1, math.floor(computed + 0.5))

    def _extract_geometry(self, title: dict) -> tuple[int | None, int | None]:
        geometry = title.get("Geometry") or {}
        if not isinstance(geometry, dict):
            return None, None
        width = geometry.get("Width")
        height = geometry.get("Height")
        if not isinstance(width, int) or width <= 0:
            width = None
        if not isinstance(height, int) or height <= 0:
            height = None
        return width, height
