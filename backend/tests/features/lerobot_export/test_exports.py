"""Tests for locating exported datasets on disk."""

from pathlib import Path

import pytest

from app.features.lerobot_export.exports import (
    EXPORTS_DIRNAME,
    exports_root,
    resolve_existing_dataset_dir,
    validate_dataset_name,
)


def test_exports_root() -> None:
    assert exports_root(Path("/data/output")).name == EXPORTS_DIRNAME


def test_validate_dataset_name_strips_and_returns() -> None:
    assert validate_dataset_name("  ds_v1  ") == "ds_v1"


@pytest.mark.parametrize("bad", ["", "   ", ".", "..", ".foo", "_foo", "a/b", "a\\b", "../x", "a b"])
def test_validate_dataset_name_rejected(bad: str) -> None:
    # Notably "." (collapses onto the exports root) and leading "." (collides with
    # the in-progress temp convention) must be rejected, not just path separators.
    with pytest.raises(ValueError):
        validate_dataset_name(bad)


def test_resolve_existing_dataset_dir(tmp_path: Path) -> None:
    (exports_root(tmp_path) / "ds_v1").mkdir(parents=True)
    resolved = resolve_existing_dataset_dir("ds_v1", tmp_path)
    assert resolved == exports_root(tmp_path) / "ds_v1"


def test_resolve_existing_dataset_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Export not found"):
        resolve_existing_dataset_dir("ghost", tmp_path)


def test_resolve_existing_dataset_dir_invalid_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_existing_dataset_dir("../escape", tmp_path)
