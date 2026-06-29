"""Tests for joint_reader cache helpers.

The MCAP-reading path (``read_joint_data`` / ``_read_from_mcap``) is marked
``pragma: no cover``; this covers the cache file naming and load/save helpers.
"""

import json
from pathlib import Path
from unittest.mock import patch

from app.features.media.joint_reader import (
    JointData,
    JointTopicsResponse,
    _cache_filename,
    _load_cache,
    _save_cache,
)


class TestCacheFilename:
    def test_no_decimation(self) -> None:
        assert _cache_filename(1) == "joint_data.json"
        assert _cache_filename(0) == "joint_data.json"

    def test_with_decimation(self) -> None:
        assert _cache_filename(20) == "joint_data_d20.json"


def _sample_response() -> JointTopicsResponse:
    return JointTopicsResponse(
        topics=[JointData(topic="/j", joint_names=["a"], timestamps=[0.0], positions=[[1.0]])]
    )


class TestSaveLoadCache:
    def test_roundtrip(self, tmp_path: Path) -> None:
        _save_cache(tmp_path, _sample_response(), decimation=1)
        loaded = _load_cache(tmp_path, decimation=1)
        assert loaded is not None
        assert loaded.topics[0].topic == "/j"

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert _load_cache(tmp_path, decimation=1) is None

    def test_load_corrupted_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "joint_data.json").write_text("not json {{{", encoding="utf-8")
        assert _load_cache(tmp_path, decimation=1) is None

    def test_load_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "joint_data.json").write_text(json.dumps({"unexpected": 1}), encoding="utf-8")
        assert _load_cache(tmp_path, decimation=1) is None

    def test_save_failure_is_swallowed(self, tmp_path: Path) -> None:
        with patch("app.features.media.joint_reader.Path.write_text", side_effect=OSError("disk full")):
            _save_cache(tmp_path, _sample_response(), decimation=1)  # no exception raised
