"""Integration tests for run_export (MCAP read patched, video sink faked)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.features.lerobot_export import converter, service, writer
from app.features.lerobot_export.models import ExportConfig, SourceConfig
from app.features.lerobot_export.validation import StructureMismatchError

from ._fakes import image_message, joint_message

MS = 1_000_000


class FakeSink:
    def __init__(self, output_paths: dict, image_shapes: dict, fps: int) -> None:
        self.output_paths = output_paths

    def write(self, camera: str, image: np.ndarray) -> None:
        pass

    def close(self) -> None:
        pass


def _config(**overrides: object) -> ExportConfig:
    base: dict = {
        "images": {"cam": "/img"},
        "observation": {"state": [SourceConfig(topic="/state", field="position")]},
        "action": [SourceConfig(topic="/cmd", field="position")],
        "fps": 10,
        "robot_type": "demo",
        "sync_tolerance_ms": 1000.0,
        "image_tolerance_ms": 1000.0,
    }
    base.update(overrides)
    return ExportConfig(**base)  # type: ignore[arg-type]


def _messages(overlap: bool = True, size: int = 2) -> dict:
    # When overlap=False, state/cmd start only after the images end, so the
    # intersection window is empty. `size` sets the camera frame resolution.
    base = 0 if overlap else 5000 * MS
    return {
        "/img": [image_message(0, size=size), image_message(100 * MS, size=size)],
        "/state": [joint_message(base, [1.0]), joint_message(base + 100 * MS, [2.0])],
        "/cmd": [joint_message(base, [9.0]), joint_message(base + 100 * MS, [8.0])],
    }


def _write_metadata(folder: Path, topics: list[str]) -> None:
    entries = "\n".join(
        f"    - topic_metadata:\n        name: {t}\n        type: sensor_msgs/msg/JointState" for t in topics
    )
    folder.joinpath("metadata.yaml").write_text(
        f"rosbag2_bagfile_information:\n  topics_with_message_count:\n{entries}\n", encoding="utf-8"
    )


def _make_recording(
    tmp_path: Path,
    name: str,
    *,
    with_mcap: bool = True,
    task: str | None = None,
    topics: list[str] | None = None,
) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    if with_mcap:
        (folder / f"{name}_0.mcap").write_bytes(b"")
    # metadata.yaml lists the config's topics so pre-export validation passes.
    _write_metadata(folder, topics if topics is not None else ["/img", "/state", "/cmd"])
    if task is not None:
        (folder / "recording_meta.json").write_text(json.dumps({"task_name": task, "tags": []}), encoding="utf-8")
    return folder


@pytest.fixture(autouse=True)
def _patch_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "VideoSink", FakeSink)


def test_run_export_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter, "read_topic_messages", lambda _path, _topics: _messages())
    rec1 = _make_recording(tmp_path, "rec1", task="pick")
    rec2 = _make_recording(tmp_path, "rec2")
    out = tmp_path / "_lerobot_exports" / "ds"

    result = service.run_export([rec1, rec2], _config(), out)

    assert result.total_episodes == 2  # one episode per recording
    assert result.total_frames == 4
    assert result.skipped == []
    info = json.loads((out / "meta" / "info.json").read_text())
    assert info["total_episodes"] == 2
    episodes = pd.read_parquet(out / "meta" / "episodes" / "chunk-000" / "file-000.parquet")
    assert list(episodes["tasks"].iloc[0]) == ["pick"]  # from recording_meta
    assert list(episodes["tasks"].iloc[1]) == ["rec2"]  # falls back to folder name


def test_run_export_records_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter, "read_topic_messages", lambda _path, _topics: _messages())
    rec = _make_recording(tmp_path, "rec1")
    steps: list[str] = []
    service.run_export([rec], _config(), tmp_path / "out", on_progress=lambda s, _c, _t: steps.append(s))
    assert steps[0] == "probe"
    assert "convert" in steps
    assert steps[-1] == "finalize"


def test_run_export_auto_fps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter, "read_topic_messages", lambda _path, _topics: _messages())
    rec = _make_recording(tmp_path, "rec1")
    out = tmp_path / "out"
    service.run_export([rec], _config(fps=0), out)  # 0 -> auto-detect
    info = json.loads((out / "meta" / "info.json").read_text())
    assert info["fps"] == 10  # two image frames 100ms apart -> 10 fps


def test_run_export_skips_recording_without_mcap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter, "read_topic_messages", lambda _path, _topics: _messages())
    rec1 = _make_recording(tmp_path, "rec1")
    rec2 = _make_recording(tmp_path, "rec2", with_mcap=False)
    result = service.run_export([rec1, rec2], _config(), tmp_path / "out")
    assert result.skipped == ["rec2"]
    assert result.total_episodes == 1


def test_run_export_no_usable_recordings(tmp_path: Path) -> None:
    rec = _make_recording(tmp_path, "rec1", with_mcap=False)
    with pytest.raises(ValueError, match="No recordings with an MCAP"):
        service.run_export([rec], _config(), tmp_path / "out")


def test_run_export_rejects_structure_mismatch(tmp_path: Path) -> None:
    rec = _make_recording(tmp_path, "rec1", topics=["/img", "/state"])  # metadata.yaml lacks /cmd
    with pytest.raises(StructureMismatchError, match="/cmd"):
        service.run_export([rec], _config(), tmp_path / "out")


def test_run_export_cleans_up_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Probe + rec1 use 2x2 frames; rec2 reads 4x4 -> shape mismatch mid-export.
    sizes = iter([2, 4])
    monkeypatch.setattr(converter, "read_topic_messages", lambda _p, _t: _messages(size=next(sizes)))
    rec1 = _make_recording(tmp_path, "rec1")
    rec2 = _make_recording(tmp_path, "rec2")
    out = tmp_path / "_lerobot_exports" / "ds"

    with pytest.raises(ValueError, match="shape mismatch"):
        service.run_export([rec1, rec2], _config(), out)

    # No partial dataset and no leftover temp dir -> the name stays reusable.
    assert not out.exists()
    assert list((tmp_path / "_lerobot_exports").iterdir()) == []


def test_run_export_skips_recording_without_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter, "read_topic_messages", lambda _path, _topics: _messages(overlap=False))
    rec = _make_recording(tmp_path, "rec1")
    out = tmp_path / "out"
    result = service.run_export([rec], _config(), out)
    assert result.total_episodes == 0  # no overlapping time range
    assert json.loads((out / "meta" / "info.json").read_text())["total_episodes"] == 0
