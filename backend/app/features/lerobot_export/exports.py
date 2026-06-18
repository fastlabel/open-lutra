"""Locating LeRobot exports on disk.

Exported datasets live under `<output_dir>/_lerobot_exports/<name>/`. The reserved
directory name keeps them out of the recordings scan (`scanner.py` skips it).
"""

from __future__ import annotations

import re
from pathlib import Path

EXPORTS_DIRNAME = "_lerobot_exports"

# Dataset names must start with an alphanumeric and contain only [A-Za-z0-9._-].
# This rejects "", path separators, "..", and leading "." / "." itself — a leading
# dot collides with the in-progress temp convention (`.<name>.*.tmp`), and "."
# collapses onto the exports root (Path / "." == exports_root), letting a rename
# clobber it.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def exports_root(output_dir: Path) -> Path:
    """Return the directory that holds all exported datasets."""
    return output_dir / EXPORTS_DIRNAME


def validate_dataset_name(name: str) -> str:
    """Return the stripped dataset name, or raise if it is not an allowed name.

    Raises:
        ValueError: If the name is empty or not an allowed dataset name.
    """
    stripped = name.strip()
    if not _NAME_RE.match(stripped):
        raise ValueError(
            "Export name must start with a letter or digit and use only letters, digits, '.', '_', '-'"
        )
    return stripped


def resolve_existing_dataset_dir(name: str, output_dir: Path) -> Path:
    """Resolve an existing dataset directory under _lerobot_exports/.

    Raises:
        ValueError: If the name is not an allowed dataset name.
        FileNotFoundError: If no dataset with that name exists.
    """
    dataset_dir = exports_root(output_dir) / validate_dataset_name(name)
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"Export not found: {name}")
    return dataset_dir
