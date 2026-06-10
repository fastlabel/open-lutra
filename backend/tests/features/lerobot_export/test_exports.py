"""Tests for listing exported datasets."""

import json
from pathlib import Path

from app.features.lerobot_export.exports import EXPORTS_DIRNAME, exports_root, list_exports


def _write_export(root: Path, name: str, *, info: dict | None = None) -> Path:
    dataset = root / name
    (dataset / "meta").mkdir(parents=True)
    if info is not None:
        (dataset / "meta" / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return dataset


def test_exports_root() -> None:
    assert exports_root(Path("/data/output")).name == EXPORTS_DIRNAME


def test_list_exports_missing_dir(tmp_path: Path) -> None:
    assert list_exports(tmp_path) == []


def test_list_exports_reads_info(tmp_path: Path) -> None:
    root = exports_root(tmp_path)
    _write_export(root, "ds_a", info={"total_episodes": 3, "total_frames": 90})
    (root / "stray_file.txt").parent.mkdir(parents=True, exist_ok=True)
    (root / "stray_file.txt").write_text("x")
    exports = list_exports(tmp_path)
    assert len(exports) == 1
    assert exports[0].name == "ds_a"
    assert exports[0].total_episodes == 3
    assert exports[0].total_frames == 90


def test_list_exports_missing_info(tmp_path: Path) -> None:
    _write_export(exports_root(tmp_path), "ds_no_info", info=None)
    exports = list_exports(tmp_path)
    assert exports[0].total_episodes is None
    assert exports[0].total_frames is None


def test_list_exports_skips_inprogress_temp_dirs(tmp_path: Path) -> None:
    root = exports_root(tmp_path)
    _write_export(root, "ds_done", info={"total_episodes": 1, "total_frames": 10})
    _write_export(root, ".ds_done.ab12.tmp", info={"total_episodes": 1, "total_frames": 10})
    names = [e.name for e in list_exports(tmp_path)]
    assert names == ["ds_done"]


def test_list_exports_invalid_info(tmp_path: Path) -> None:
    dataset = exports_root(tmp_path) / "ds_bad"
    (dataset / "meta").mkdir(parents=True)
    (dataset / "meta" / "info.json").write_text("{not json", encoding="utf-8")
    exports = list_exports(tmp_path)
    assert exports[0].total_episodes is None
