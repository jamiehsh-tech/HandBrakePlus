"""Domain models for HandBrakePlus jobs, presets, and clip ranges."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PresetTemplate:
    """A reusable HandBrake encoding template."""

    name: str
    description: str
    handbrake_args: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClipRange:
    """A frame-based clip extracted from a source video."""

    start_frame: int
    end_frame: int
    index: int
    frame_count: int | None = None

    @property
    def label(self) -> str:
        return f"{self.index}"

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame + 1)


@dataclass(slots=True)
class VideoSource:
    """A user-imported video file."""

    path: Path
    ranges: list[ClipRange] = field(default_factory=list)
    total_frames: int | None = None
    width: int | None = None
    height: int | None = None
    probe_error: str = ""

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def max_frame_index(self) -> int | None:
        if self.total_frames is None:
            return None
        return max(0, self.total_frames - 1)


@dataclass(slots=True)
class EncodeJob:
    """A single queued encode operation."""

    source_path: Path
    output_path: Path
    preset_name: str
    preset_args: list[str]
    start_frame: int
    end_frame: int
    display_name: str


@dataclass(slots=True)
class JobProgress:
    """Status snapshot for the active encode job."""

    status: str
    message: str = ""
    percent: float | None = None
    current_job: str | None = None
    completed_jobs: int = 0
    total_jobs: int = 0
    extra: dict[str, Any] = field(default_factory=dict)
