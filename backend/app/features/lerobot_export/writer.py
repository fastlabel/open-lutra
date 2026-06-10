"""LeRobot v3.0 dataset writer (self-implemented, no `lerobot` dependency).

Accumulates synchronized frames and writes a v3.0 dataset directory:

    <root>/meta/{info.json,stats.json,tasks.parquet,episodes/chunk-000/file-000.parquet}
    <root>/data/chunk-000/file-000.parquet
    <root>/videos/observation.images.<cam>/chunk-000/file-000.mp4

MVP scope: a single `chunk-000/file-000` shard for the data parquet and for each
camera video; size-based sharding is not implemented (a warning is logged if a
shard exceeds the default thresholds). Spec verified against huggingface/lerobot
`CODEBASE_VERSION = "v3.0"`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
import pandas as pd

from app.features.lerobot_export.stats import ImageStats, StatsAccumulator, VectorStats
from app.features.lerobot_export.video_sink import VideoSink

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from app.features.lerobot_export.converter import Frame
    from app.features.lerobot_export.models import FeatureSpec

logger = logging.getLogger(__name__)

CODEBASE_VERSION = "v3.0"
CHUNKS_SIZE = 1000
DATA_FILES_SIZE_IN_MB = 100
VIDEO_FILES_SIZE_IN_MB = 200
DATA_PATH_TEMPLATE = "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
VIDEO_PATH_TEMPLATE = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
EPISODES_PATH_TEMPLATE = "meta/episodes/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"

class FrameSink(Protocol):
    """Structural type for the per-camera video encoder (so tests can inject a fake)."""

    def write(self, camera: str, image: NDArray[np.uint8]) -> None: ...

    def close(self) -> None: ...


# Factory signature: (output_paths, image_shapes, fps) -> sink. Default is VideoSink.
SinkFactory = Callable[[dict[str, Path], dict[str, tuple[int, int, int]], int], FrameSink]


class LeRobotV30Writer:
    """Streaming writer for a single LeRobot v3.0 dataset."""

    def __init__(
        self,
        root: Path,
        fps: int,
        robot_type: str,
        spec: FeatureSpec,
        *,
        sink_factory: SinkFactory | None = None,
    ) -> None:
        self._root = root
        self._fps = fps
        self._robot_type = robot_type
        self._spec = spec
        self._sink_factory = sink_factory
        self._video_keys = [f"observation.images.{cam}" for cam in spec.camera_names]

        # Per-frame buffers (numeric only; small).
        self._actions: list[NDArray[np.float32]] = []
        self._obs: dict[str, list[NDArray[np.float32]]] = {name: [] for name in spec.observation_fields}
        self._timestamps: list[float] = []
        self._frame_indices: list[int] = []
        self._episode_indices: list[int] = []
        self._global_indices: list[int] = []
        self._task_indices: list[int] = []

        self._tasks: list[str] = []
        self._task_to_index: dict[str, int] = {}
        self._episodes: list[dict[str, Any]] = []

        self._global_stats = self._new_accumulators()
        self._ep_stats = self._new_accumulators()
        self._index = 0
        self._episode_counter = 0
        self._cur_ep_count = 0
        self._cur_ep_tasks: set[str] = set()
        self._sink: FrameSink | None = None

    @property
    def total_episodes(self) -> int:
        """Number of finalized (non-empty) episodes written so far."""
        return self._episode_counter

    @property
    def total_frames(self) -> int:
        """Number of frames written so far across all episodes."""
        return self._index

    def __enter__(self) -> LeRobotV30Writer:
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def open(self) -> None:
        """Create the directory tree and open the video encoders."""
        (self._root / "meta" / "episodes" / "chunk-000").mkdir(parents=True, exist_ok=True)
        (self._root / "data" / "chunk-000").mkdir(parents=True, exist_ok=True)
        output_paths = {
            cam: self._root / VIDEO_PATH_TEMPLATE.format(video_key=key, chunk_index=0, file_index=0)
            for cam, key in zip(self._spec.camera_names, self._video_keys, strict=True)
        }
        factory: SinkFactory = self._sink_factory or VideoSink
        self._sink = factory(output_paths, self._spec.image_shapes, self._fps)

    def add_frame(self, frame: Frame) -> None:
        """Append one synchronized frame: encode its images and buffer its vectors."""
        if self._sink is None:
            raise RuntimeError("Writer must be opened before adding frames")

        for camera, image in frame.camera_images.items():
            # All recordings must share each camera's resolution: the video shape
            # is probed once from the first recording and the sink pipes raw bytes
            # at that fixed size, so a differently-sized frame would silently
            # corrupt the MP4. Fail loudly instead.
            expected = self._spec.image_shapes[camera]
            if tuple(image.shape) != expected:
                raise ValueError(
                    f"Image shape mismatch for camera {camera!r}: got {tuple(image.shape)}, "
                    f"expected {expected}. All recordings must share the same camera resolution."
                )
            self._sink.write(camera, image)
            self._global_stats[f"observation.images.{camera}"].add(image)
            self._ep_stats[f"observation.images.{camera}"].add(image)

        action = frame.action.astype(np.float32)
        self._actions.append(action)
        self._global_stats["action"].add(frame.action)
        self._ep_stats["action"].add(frame.action)
        for field_name, values in frame.observations.items():
            self._obs[field_name].append(values.astype(np.float32))
            self._global_stats[f"observation.{field_name}"].add(values)
            self._ep_stats[f"observation.{field_name}"].add(values)

        task_index = self._resolve_task_index(frame.task)
        self._timestamps.append(self._cur_ep_count / self._fps)
        self._frame_indices.append(self._cur_ep_count)
        self._episode_indices.append(self._episode_counter)
        self._global_indices.append(self._index)
        self._task_indices.append(task_index)
        self._cur_ep_tasks.add(frame.task)
        self._cur_ep_count += 1
        self._index += 1

    def end_episode(self) -> None:
        """Finalize the current episode (no-op if it produced no frames)."""
        if self._cur_ep_count == 0:
            self._ep_stats = self._new_accumulators()
            self._cur_ep_tasks = set()
            return

        to_index = self._index
        from_index = self._index - self._cur_ep_count
        self._episodes.append(
            {
                "episode_index": self._episode_counter,
                "dataset_from_index": from_index,
                "dataset_to_index": to_index,
                "from_timestamp": from_index / self._fps,
                "to_timestamp": to_index / self._fps,
                "tasks": sorted(self._cur_ep_tasks),
                "length": self._cur_ep_count,
                "stats": {feature: accum.stats() for feature, accum in self._ep_stats.items()},
            }
        )
        self._episode_counter += 1
        self._cur_ep_count = 0
        self._cur_ep_tasks = set()
        self._ep_stats = self._new_accumulators()

    def close(self) -> None:
        """Close the encoders and write all parquet/metadata files."""
        if self._sink is not None:
            self._sink.close()
            self._sink = None
        self._write_data_parquet()
        self._write_episodes_parquet()
        self._write_tasks_parquet()
        self._write_stats_json()
        self._write_info_json()
        logger.info(
            "LeRobot dataset written: %s (%d episodes, %d frames)",
            self._root,
            self._episode_counter,
            self._index,
        )

    # --- internals ---

    def _new_accumulators(self) -> dict[str, StatsAccumulator]:
        accumulators: dict[str, StatsAccumulator] = {"action": VectorStats(self._spec.action_dim)}
        for field_name, (dim, _names) in self._spec.observation_fields.items():
            accumulators[f"observation.{field_name}"] = VectorStats(dim)
        for camera in self._spec.camera_names:
            accumulators[f"observation.images.{camera}"] = ImageStats(self._spec.image_shapes[camera][2])
        return accumulators

    def _resolve_task_index(self, task: str) -> int:
        if task not in self._task_to_index:
            self._task_to_index[task] = len(self._tasks)
            self._tasks.append(task)
        return self._task_to_index[task]

    def _write_data_parquet(self) -> None:
        columns: dict[str, object] = {"action": self._actions}
        for field_name, rows in self._obs.items():
            columns[f"observation.{field_name}"] = rows
        columns["timestamp"] = np.asarray(self._timestamps, dtype=np.float32)
        columns["frame_index"] = np.asarray(self._frame_indices, dtype=np.int64)
        columns["episode_index"] = np.asarray(self._episode_indices, dtype=np.int64)
        columns["index"] = np.asarray(self._global_indices, dtype=np.int64)
        columns["task_index"] = np.asarray(self._task_indices, dtype=np.int64)
        path = self._root / DATA_PATH_TEMPLATE.format(chunk_index=0, file_index=0)
        pd.DataFrame(columns).to_parquet(path, index=False)
        self._warn_if_oversized(path, DATA_FILES_SIZE_IN_MB, "data")

    def _write_episodes_parquet(self) -> None:
        columns: dict[str, list[Any]] = {
            "episode_index": [ep["episode_index"] for ep in self._episodes],
            "data/chunk_index": [0] * len(self._episodes),
            "data/file_index": [0] * len(self._episodes),
            "dataset_from_index": [ep["dataset_from_index"] for ep in self._episodes],
            "dataset_to_index": [ep["dataset_to_index"] for ep in self._episodes],
        }
        for video_key in self._video_keys:
            columns[f"videos/{video_key}/chunk_index"] = [0] * len(self._episodes)
            columns[f"videos/{video_key}/file_index"] = [0] * len(self._episodes)
            columns[f"videos/{video_key}/from_timestamp"] = [ep["from_timestamp"] for ep in self._episodes]
            columns[f"videos/{video_key}/to_timestamp"] = [ep["to_timestamp"] for ep in self._episodes]
        columns["tasks"] = [ep["tasks"] for ep in self._episodes]
        columns["length"] = [ep["length"] for ep in self._episodes]
        for feature in self._global_stats:
            for stat in ("min", "max", "mean", "std", "count"):
                columns[f"stats/{feature}/{stat}"] = [ep["stats"][feature][stat] for ep in self._episodes]
        path = self._root / EPISODES_PATH_TEMPLATE.format(chunk_index=0, file_index=0)
        pd.DataFrame(columns).to_parquet(path, index=False)

    def _write_tasks_parquet(self) -> None:
        path = self._root / "meta" / "tasks.parquet"
        frame = pd.DataFrame(
            {"task_index": list(range(len(self._tasks)))},
            index=pd.Index(self._tasks, name="task"),
        )
        frame.to_parquet(path)

    def _write_stats_json(self) -> None:
        stats = {feature: accum.stats() for feature, accum in self._global_stats.items()}
        path = self._root / "meta" / "stats.json"
        path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_info_json(self) -> None:
        info = {
            "codebase_version": CODEBASE_VERSION,
            "robot_type": self._robot_type,
            "total_episodes": self._episode_counter,
            "total_frames": self._index,
            "total_tasks": len(self._tasks),
            "chunks_size": CHUNKS_SIZE,
            "fps": self._fps,
            "splits": {"train": f"0:{self._episode_counter}"},
            "data_path": DATA_PATH_TEMPLATE,
            "video_path": VIDEO_PATH_TEMPLATE,
            "features": self._build_features(),
            "data_files_size_in_mb": DATA_FILES_SIZE_IN_MB,
            "video_files_size_in_mb": VIDEO_FILES_SIZE_IN_MB,
        }
        path = self._root / "meta" / "info.json"
        path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_features(self) -> dict[str, dict[str, Any]]:
        features: dict[str, dict[str, Any]] = {
            "action": {
                "dtype": "float32",
                "shape": [self._spec.action_dim],
                "names": self._spec.action_names,
                "fps": self._fps,
            }
        }
        for field_name, (dim, names) in self._spec.observation_fields.items():
            features[f"observation.{field_name}"] = {
                "dtype": "float32",
                "shape": [dim],
                "names": names,
                "fps": self._fps,
            }
        for camera in self._spec.camera_names:
            height, width, channels = self._spec.image_shapes[camera]
            features[f"observation.images.{camera}"] = {
                "dtype": "video",
                "shape": [height, width, channels],
                "names": ["height", "width", "channels"],
                "info": {
                    "video.fps": float(self._fps),
                    "video.height": height,
                    "video.width": width,
                    "video.channels": channels,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "has_audio": False,
                },
            }
        for name in ("timestamp",):
            features[name] = {"dtype": "float32", "shape": [1], "names": None, "fps": self._fps}
        for name in ("frame_index", "episode_index", "index", "task_index"):
            features[name] = {"dtype": "int64", "shape": [1], "names": None, "fps": self._fps}
        return features

    def _warn_if_oversized(self, path: Path, limit_mb: int, label: str) -> None:
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > limit_mb:
            logger.warning(
                "%s shard %s is %.1f MB (> %d MB threshold); sharding is not implemented, "
                "so this dataset uses a single oversized file.",
                label,
                path.name,
                size_mb,
                limit_mb,
            )
