"""Tests for the LeRobot v3.0 writer (metadata + parquet), using a fake video sink."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.features.lerobot_export.converter import Frame
from app.features.lerobot_export.models import FeatureSpec
from app.features.lerobot_export.writer import LeRobotV30Writer


class FakeSink:
    """Records frames per camera instead of encoding video."""

    def __init__(self, output_paths: dict, image_shapes: dict, fps: int) -> None:
        self.output_paths = output_paths
        self.writes: dict[str, int] = dict.fromkeys(output_paths, 0)
        self.closed = False

    def write(self, camera: str, image: np.ndarray) -> None:
        self.writes[camera] += 1

    def close(self) -> None:
        self.closed = True


def _spec() -> FeatureSpec:
    return FeatureSpec(
        camera_names=["cam"],
        image_shapes={"cam": (2, 2, 3)},
        observation_fields={"state": (2, ["j0", "j1"])},
        action_dim=2,
        action_names=["a0", "a1"],
    )


def _frame(value: float, task: str = "pick") -> Frame:
    return Frame(
        camera_images={"cam": np.full((2, 2, 3), int(value), dtype=np.uint8)},
        observations={"state": np.array([value, value + 1])},
        action=np.array([value + 2, value + 3]),
        task=task,
    )


@pytest.fixture
def written(tmp_path: Path) -> tuple[Path, FakeSink]:
    sinks: list[FakeSink] = []

    def factory(paths: dict, shapes: dict, fps: int) -> FakeSink:
        sink = FakeSink(paths, shapes, fps)
        sinks.append(sink)
        return sink

    writer = LeRobotV30Writer(tmp_path, fps=10, robot_type="demo", spec=_spec(), sink_factory=factory)
    with writer:
        writer.add_frame(_frame(1.0))
        writer.add_frame(_frame(3.0))
        writer.end_episode()
        writer.end_episode()  # empty episode -> no-op
        writer.add_frame(_frame(5.0, task="place"))
        writer.end_episode()
    return tmp_path, sinks[0]


def test_directory_layout(written: tuple[Path, FakeSink]) -> None:
    root, _ = written
    assert (root / "meta" / "info.json").exists()
    assert (root / "meta" / "stats.json").exists()
    assert (root / "meta" / "tasks.parquet").exists()
    assert (root / "meta" / "episodes" / "chunk-000" / "file-000.parquet").exists()
    assert (root / "data" / "chunk-000" / "file-000.parquet").exists()


def test_sink_received_all_frames(written: tuple[Path, FakeSink]) -> None:
    _, sink = written
    assert sink.writes["cam"] == 3
    assert sink.closed is True


def test_info_json(written: tuple[Path, FakeSink]) -> None:
    root, _ = written
    info = json.loads((root / "meta" / "info.json").read_text())
    assert info["codebase_version"] == "v3.0"
    assert info["total_episodes"] == 2
    assert info["total_frames"] == 3
    assert info["total_tasks"] == 2
    assert info["fps"] == 10
    assert info["splits"] == {"train": "0:2"}
    assert info["features"]["action"]["shape"] == [2]
    assert info["features"]["action"]["dtype"] == "float32"
    assert info["features"]["observation.images.cam"]["dtype"] == "video"
    assert info["features"]["observation.images.cam"]["shape"] == [2, 2, 3]
    assert info["features"]["observation.images.cam"]["info"]["video.codec"] == "h264"
    assert info["features"]["timestamp"]["dtype"] == "float32"
    assert info["features"]["frame_index"]["dtype"] == "int64"


def test_data_parquet(written: tuple[Path, FakeSink]) -> None:
    root, _ = written
    df = pd.read_parquet(root / "data" / "chunk-000" / "file-000.parquet")
    assert list(df["frame_index"]) == [0, 1, 0]  # resets per episode
    assert list(df["index"]) == [0, 1, 2]  # global, monotonic
    assert list(df["episode_index"]) == [0, 0, 1]
    assert list(df["task_index"]) == [0, 0, 1]
    assert df["timestamp"].tolist() == pytest.approx([0.0, 0.1, 0.0])
    assert list(df["action"].iloc[0]) == [3.0, 4.0]
    assert list(df["observation.state"].iloc[0]) == [1.0, 2.0]


def test_episodes_parquet(written: tuple[Path, FakeSink]) -> None:
    root, _ = written
    df = pd.read_parquet(root / "meta" / "episodes" / "chunk-000" / "file-000.parquet")
    assert list(df["episode_index"]) == [0, 1]
    assert list(df["length"]) == [2, 1]
    assert list(df["dataset_from_index"]) == [0, 2]
    assert list(df["dataset_to_index"]) == [2, 3]
    assert list(df["tasks"].iloc[0]) == ["pick"]
    assert list(df["tasks"].iloc[1]) == ["place"]
    assert df["videos/observation.images.cam/from_timestamp"].iloc[1] == pytest.approx(0.2)
    assert "stats/action/mean" in df.columns


def test_tasks_parquet(written: tuple[Path, FakeSink]) -> None:
    root, _ = written
    df = pd.read_parquet(root / "meta" / "tasks.parquet")
    assert df.index.name == "task"
    assert list(df.index) == ["pick", "place"]
    assert list(df["task_index"]) == [0, 1]


def test_stats_json(written: tuple[Path, FakeSink]) -> None:
    root, _ = written
    stats = json.loads((root / "meta" / "stats.json").read_text())
    assert stats["action"]["count"] == [3]
    assert stats["action"]["min"] == [3.0, 4.0]
    # Frames are filled with 1/3/5; min normalized pixel = 1/255 per channel.
    assert stats["observation.images.cam"]["count"] == [3]
    assert stats["observation.images.cam"]["min"][0][0][0] == pytest.approx(1 / 255)


def test_add_frame_before_open(tmp_path: Path) -> None:
    writer = LeRobotV30Writer(tmp_path, fps=10, robot_type="demo", spec=_spec(), sink_factory=FakeSink)
    with pytest.raises(RuntimeError, match="must be opened"):
        writer.add_frame(_frame(1.0))


def test_warn_if_oversized(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    writer = LeRobotV30Writer(tmp_path, fps=10, robot_type="demo", spec=_spec(), sink_factory=FakeSink)
    probe = tmp_path / "probe.bin"
    probe.write_bytes(b"x" * 2048)
    writer._warn_if_oversized(probe, limit_mb=0, label="data")  # forces the warning branch
    assert "sharding is not implemented" in caplog.text
    writer._warn_if_oversized(probe, limit_mb=100, label="data")  # under threshold, no warning
