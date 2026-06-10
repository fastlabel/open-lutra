"""Listing of existing LeRobot exports on disk.

Exported datasets live under `<output_dir>/_lerobot_exports/<name>/`. The leading
underscore keeps them out of the recordings scan (`scanner.py` skips names
starting with `_`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EXPORTS_DIRNAME = "_lerobot_exports"


@dataclass(frozen=True, slots=True)
class ExportInfo:
    """Summary of one exported dataset (read from its meta/info.json)."""

    name: str
    total_episodes: int | None
    total_frames: int | None


def exports_root(output_dir: Path) -> Path:
    """Return the directory that holds all exported datasets."""
    return output_dir / EXPORTS_DIRNAME


def list_exports(output_dir: Path) -> list[ExportInfo]:
    """List exported datasets under `<output_dir>/_lerobot_exports/`, newest first."""
    root = exports_root(output_dir)
    if not root.is_dir():
        return []

    infos: list[tuple[float, ExportInfo]] = []
    for item in root.iterdir():
        # Skip in-progress export temp dirs (`.<name>.*.tmp`, renamed in on success).
        if not item.is_dir() or item.name.startswith("."):
            continue
        episodes, frames = _read_info_totals(item)
        infos.append((item.stat().st_mtime, ExportInfo(name=item.name, total_episodes=episodes, total_frames=frames)))

    infos.sort(key=lambda pair: pair[0], reverse=True)
    return [info for _mtime, info in infos]


def _read_info_totals(dataset_dir: Path) -> tuple[int | None, int | None]:
    info_path = dataset_dir / "meta" / "info.json"
    if not info_path.exists():
        return None, None
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to read export info.json (%s): %s", info_path, e)
        return None, None
    return data.get("total_episodes"), data.get("total_frames")
