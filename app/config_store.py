"""Load and save HandBrakePlus local configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import PresetTemplate


LEGACY_DEFAULT_HANDBRAKE_PATH = r"C:\Program Files\HandBrake\HandBrakeCLI.exe"
DEFAULT_HANDBRAKE_PATH = r"C:\Program Files\HandBrakeCLI\HandBrakeCLI.exe"

DEFAULT_PRESET_ITEMS = [
    {
        "name": "1080p H.265 NVENC 4000kbps VFR",
        "description": "1080p H.265 NVENC, average bitrate 4000 kbps, source-matched color range, Medium preset, rc-lookahead=10, audio AAC 256 stereo, variable frame rate.",
        "handbrake_args": [
            "--format",
            "av_mp4",
            "--encoder",
            "nvenc_h265",
            "--encoder-preset",
            "medium",
            "--vb",
            "4000",
            "--vfr",
            "--color-range",
            "auto",
            "--maxWidth",
            "1920",
            "--maxHeight",
            "1080",
            "--encopts",
            "rc-lookahead=10",
            "--aencoder",
            "av_aac",
            "--ab",
            "256",
            "--mixdown",
            "stereo",
            "--arate",
            "auto",
        ],
    },
    {
        "name": "4K H.265 NVENC 10Mbps VFR",
        "description": "4K H.265 NVENC, average bitrate 10000 kbps, source-matched color range, Medium preset, rc-lookahead=10, audio AAC 256 stereo, variable frame rate.",
        "handbrake_args": [
            "--format",
            "av_mp4",
            "--encoder",
            "nvenc_h265",
            "--encoder-preset",
            "medium",
            "--vb",
            "10000",
            "--vfr",
            "--color-range",
            "auto",
            "--maxWidth",
            "3840",
            "--maxHeight",
            "2160",
            "--encopts",
            "rc-lookahead=10",
            "--aencoder",
            "av_aac",
            "--ab",
            "256",
            "--mixdown",
            "stereo",
            "--arate",
            "auto",
        ],
    },
    {
        "name": "720p H.265 NVENC 2000kbps VFR",
        "description": "720p H.265 NVENC, average bitrate 2000 kbps, source-matched color range, Medium preset, rc-lookahead=10, audio AAC 256 stereo, variable frame rate.",
        "handbrake_args": [
            "--format",
            "av_mp4",
            "--encoder",
            "nvenc_h265",
            "--encoder-preset",
            "medium",
            "--vb",
            "2000",
            "--vfr",
            "--color-range",
            "auto",
            "--maxWidth",
            "1280",
            "--maxHeight",
            "720",
            "--encopts",
            "rc-lookahead=10",
            "--aencoder",
            "av_aac",
            "--ab",
            "256",
            "--mixdown",
            "stereo",
            "--arate",
            "auto",
        ],
    },
    {
        "name": "Balanced H.265 CPU",
        "description": "Fallback x265 preset when NVENC is not available.",
        "handbrake_args": ["--format", "av_mp4", "--encoder", "x265", "--quality", "20", "--vfr", "--aencoder", "av_aac", "--ab", "256", "--mixdown", "stereo", "--arate", "auto"],
    },
]


DEFAULT_CONFIG = {
    "handbrake_path": DEFAULT_HANDBRAKE_PATH,
    "default_output_dir": "",
    "last_preset": "4K H.265 NVENC 10Mbps VFR",
    "presets": DEFAULT_PRESET_ITEMS,
}


class ConfigStore:
    """Persist local app settings as JSON."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.path = base_dir / "config.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_CONFIG))
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        merged = self._merge_defaults(data)
        if merged != data:
            self.save(merged)
        return merged

    def save(self, data: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def load_presets(self) -> list[PresetTemplate]:
        data = self.load()
        return self.deserialize_presets(data)

    def deserialize_presets(self, data: dict[str, Any]) -> list[PresetTemplate]:
        presets: list[PresetTemplate] = []
        for item in data.get("presets", []):
            presets.append(
                PresetTemplate(
                    name=item["name"],
                    description=item.get("description", ""),
                    handbrake_args=list(item.get("handbrake_args", [])),
                )
            )
        return presets

    def _merge_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        merged.update({k: v for k, v in data.items() if k != "presets"})
        if merged.get("handbrake_path") == LEGACY_DEFAULT_HANDBRAKE_PATH:
            merged["handbrake_path"] = DEFAULT_HANDBRAKE_PATH
        merged["presets"] = self._merge_presets(data.get("presets"))
        return merged

    def _merge_presets(self, current_presets: Any) -> list[dict[str, Any]]:
        if not isinstance(current_presets, list):
            return json.loads(json.dumps(DEFAULT_PRESET_ITEMS))

        default_by_name = {item["name"]: item for item in DEFAULT_PRESET_ITEMS}
        merged_presets: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for item in current_presets:
            if not isinstance(item, dict) or "name" not in item:
                continue
            name = item["name"]
            if name in default_by_name:
                merged_presets.append(json.loads(json.dumps(default_by_name[name])))
            else:
                merged_presets.append(
                    {
                        "name": name,
                        "description": item.get("description", ""),
                        "handbrake_args": list(item.get("handbrake_args", [])),
                    }
                )
            seen_names.add(name)

        for item in DEFAULT_PRESET_ITEMS:
            if item["name"] not in seen_names:
                merged_presets.append(json.loads(json.dumps(item)))

        return merged_presets
