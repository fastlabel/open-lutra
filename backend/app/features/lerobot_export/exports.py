"""Locating LeRobot exports on disk.

Exported datasets live under `<output_dir>/_lerobot_exports/<name>/`. The reserved
directory name keeps them out of the recordings scan (`scanner.py` skips it).
"""

from __future__ import annotations

from pathlib import Path

EXPORTS_DIRNAME = "_lerobot_exports"


def exports_root(output_dir: Path) -> Path:
    """Return the directory that holds all exported datasets."""
    return output_dir / EXPORTS_DIRNAME
