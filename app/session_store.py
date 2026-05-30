"""Persist imported sources, ranges, and queued jobs between app launches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ClipRange, EncodeJob, VideoSource


class SessionStore:
    """Save and restore the current app session as JSON."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.path = base_dir / "session.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"sources": [], "batch_jobs": []}
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, sources: list[VideoSource], batch_jobs: list[EncodeJob]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "sources": [self._serialize_source(source) for source in sources],
            "batch_jobs": [self._serialize_job(job) for job in batch_jobs],
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def export_sources(self, export_path: Path, sources: list[VideoSource]) -> None:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "sources": [self._serialize_source(source) for source in sources],
        }
        with export_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def import_sources(self, import_path: Path) -> list[VideoSource]:
        with import_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Invalid import file format.")
        return self.restore_sources(payload)

    def _serialize_source(self, source: VideoSource) -> dict[str, Any]:
        return {
            "path": str(source.path),
            "total_frames": source.total_frames,
            "probe_error": source.probe_error,
            "ranges": [
                {
                    "start_frame": clip.start_frame,
                    "end_frame": clip.end_frame,
                    "index": clip.index,
                    "frame_count": clip.frame_count,
                }
                for clip in source.ranges
            ],
        }

    def _serialize_job(self, job: EncodeJob) -> dict[str, Any]:
        return {
            "source_path": str(job.source_path),
            "output_path": str(job.output_path),
            "preset_name": job.preset_name,
            "preset_args": list(job.preset_args),
            "start_frame": job.start_frame,
            "end_frame": job.end_frame,
            "display_name": job.display_name,
        }

    def restore_sources(self, payload: dict[str, Any]) -> list[VideoSource]:
        sources: list[VideoSource] = []
        for item in payload.get("sources", []):
            source = VideoSource(
                path=Path(item["path"]),
                total_frames=item.get("total_frames"),
                probe_error=item.get("probe_error", ""),
            )
            for clip_data in item.get("ranges", []):
                source.ranges.append(
                    ClipRange(
                        start_frame=clip_data["start_frame"],
                        end_frame=clip_data["end_frame"],
                        index=clip_data["index"],
                        frame_count=clip_data.get("frame_count"),
                    )
                )
            sources.append(source)
        return sources

    def restore_jobs(self, payload: dict[str, Any]) -> list[EncodeJob]:
        jobs: list[EncodeJob] = []
        for item in payload.get("batch_jobs", []):
            jobs.append(
                EncodeJob(
                    source_path=Path(item["source_path"]),
                    output_path=Path(item["output_path"]),
                    preset_name=item["preset_name"],
                    preset_args=list(item.get("preset_args", [])),
                    start_frame=item["start_frame"],
                    end_frame=item["end_frame"],
                    display_name=item["display_name"],
                )
            )
        return jobs
