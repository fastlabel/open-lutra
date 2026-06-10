"""Tests for the export router's pure helpers (HTTP glue is pragma: no cover)."""

from pathlib import Path

import pytest

from app.features.lerobot_export import router
from app.features.lerobot_export.config_loader import parse_config
from app.features.lerobot_export.exports import EXPORTS_DIRNAME

_MAPPING = {
    "fps": 15,
    "robot_type": "demo",
    "images": {"cam": "/img"},
    "observation": {"state": [{"topic": "/s", "field": "position"}]},
    "action": [{"topic": "/c", "field": "position"}],
}


def test_build_config_info_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "has_active_config", lambda: True)
    monkeypatch.setattr(router, "load_active_config", lambda: parse_config(_MAPPING))
    info = router.build_config_info()
    assert info.configured is True
    assert info.robot_type == "demo"
    assert info.cameras == ["cam"]


def test_build_config_info_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "has_active_config", lambda: False)
    info = router.build_config_info()
    assert info.configured is False
    assert info.robot_type is None
    assert info.cameras == []


def test_resolve_source_dirs(tmp_path: Path) -> None:
    (tmp_path / "rec1").mkdir()
    (tmp_path / "rec2").mkdir()
    resolved = router.resolve_source_dirs(["rec1", "rec2"], tmp_path)
    assert [p.name for p in resolved] == ["rec1", "rec2"]


def test_resolve_source_dirs_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No recordings selected"):
        router.resolve_source_dirs([], tmp_path)


def test_resolve_source_dirs_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid folder path"):
        router.resolve_source_dirs(["../escape"], tmp_path)


def test_resolve_source_dirs_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        router.resolve_source_dirs(["ghost"], tmp_path)


def test_resolve_dataset_dir(tmp_path: Path) -> None:
    out = router.resolve_dataset_dir("my_dataset", tmp_path)
    assert out.parent.name == EXPORTS_DIRNAME
    assert out.name == "my_dataset"


def test_resolve_dataset_dir_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        router.resolve_dataset_dir("   ", tmp_path)


@pytest.mark.parametrize("bad", ["a/b", "a\\b", "../x"])
def test_resolve_dataset_dir_separators(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="path separators"):
        router.resolve_dataset_dir(bad, tmp_path)
