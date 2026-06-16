"""MCAP → frame-stream conversion.

Reads per-topic messages, builds a uniform fps timebase over each recording,
aligns images (nearest + forward-fill) and interpolates state/action sources,
then emits synchronized frames. A frame is dropped if any image or any source
has no value at its timestamp.

Timestamps come from the project's `header.stamp`-preferred `resolve_timestamp_ns`
rather than raw `log_time`, consistent with the rest of the codebase.

The message-reading entry point touches MCAP I/O (pragma: no cover); the
alignment / resampling / framing logic is pure and unit-tested.
"""

from __future__ import annotations

import bisect
import logging
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from app.features.lerobot_export.extract import decode_ros_image, extract_field_data
from app.features.lerobot_export.interpolation import TimestampedValue, get_interpolator
from app.features.lerobot_export.models import ExportConfig, FeatureSpec, SourceConfig
from app.infra.mcap import MCAPReader, resolve_timestamp_ns

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TimestampedMessage:
    """A decoded message paired with its resolved timestamp (nanoseconds)."""

    timestamp_ns: int
    decoded: Any


@dataclass(slots=True)
class Frame:
    """One synchronized frame ready to be written to the dataset."""

    camera_images: dict[str, NDArray[np.uint8]]
    observations: dict[str, NDArray[np.float64]]
    action: NDArray[np.float64]
    task: str


def read_topic_messages(
    mcap_path: Path,
    topics: list[str],
) -> dict[str, list[TimestampedMessage]]:  # pragma: no cover
    """Read every message for `topics`, grouped by topic and sorted by timestamp."""
    result: dict[str, list[TimestampedMessage]] = defaultdict(list)
    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages(topics=topics):
            ts = resolve_timestamp_ns(msg.decoded, msg.timestamp_ns)
            result[msg.topic].append(TimestampedMessage(timestamp_ns=ts, decoded=msg.decoded))
    for messages in result.values():
        messages.sort(key=lambda m: m.timestamp_ns)
    return result


def detect_fps(messages_by_topic: dict[str, list[TimestampedMessage]], image_topics: list[str]) -> int:
    """Estimate fps from the first image topic with at least two messages.

    Falls back to 30 when no image topic carries enough messages.
    """
    for topic in image_topics:
        messages = messages_by_topic.get(topic, [])
        if len(messages) >= 2:
            span_ns = messages[-1].timestamp_ns - messages[0].timestamp_ns
            if span_ns > 0:
                return max(round((len(messages) - 1) * 1e9 / span_ns), 1)
    return 30


def compute_ref_timestamps(
    messages_by_topic: dict[str, list[TimestampedMessage]],
    fps: int,
    time_range: str,
) -> list[int]:
    """Build the uniform fps timebase over all non-empty topics.

    `intersection` spans only the window where every topic has data;
    `union` spans the full extent. Returns [] when no topic has messages or
    (for intersection) the windows do not overlap.
    """
    non_empty = [messages for messages in messages_by_topic.values() if messages]
    if not non_empty:
        return []

    if time_range == "union":
        first_ts = min(messages[0].timestamp_ns for messages in non_empty)
        last_ts = max(messages[-1].timestamp_ns for messages in non_empty)
    else:
        first_ts = max(messages[0].timestamp_ns for messages in non_empty)
        last_ts = min(messages[-1].timestamp_ns for messages in non_empty)
        if first_ts > last_ts:
            return []

    interval_ns = max(int(1e9 / fps), 1)
    return list(range(first_ts, last_ts + 1, interval_ns))


def probe_feature_spec(
    probe_messages: dict[str, list[TimestampedMessage]],
    config: ExportConfig,
) -> FeatureSpec:
    """Resolve image shapes and observation/action dimensions from sample messages.

    Raises:
        ValueError: When a referenced topic has no messages in the probe set.
    """
    image_shapes: dict[str, tuple[int, int, int]] = {}
    for camera_name, topic in config.images.items():
        messages = probe_messages.get(topic) or []
        if not messages:
            raise ValueError(f"No messages for image topic: {topic}")
        sample = decode_ros_image(messages[0].decoded)
        image_shapes[camera_name] = (sample.shape[0], sample.shape[1], sample.shape[2])

    observation_fields: dict[str, tuple[int, list[str]]] = {
        field_name: _probe_sources(probe_messages, field_name, sources)
        for field_name, sources in config.observation.items()
    }
    action_dim, action_names = _probe_sources(probe_messages, "action", config.action)

    return FeatureSpec(
        camera_names=list(config.images.keys()),
        image_shapes=image_shapes,
        observation_fields=observation_fields,
        action_dim=action_dim,
        action_names=action_names,
    )


def iter_episode_frames(
    messages_by_topic: dict[str, list[TimestampedMessage]],
    config: ExportConfig,
    ref_timestamps: list[int],
    task: str,
) -> Iterator[Frame]:
    """Yield synchronized frames for one recording (= one episode).

    Drops any frame where an image or a state/action source has no value at its
    timestamp. Images are decoded lazily (one frame at a time) to bound memory;
    the small state/action vectors are resampled up front.
    """
    episode_ts = ref_timestamps
    sync_tolerance_ns = int(config.sync_tolerance_ms * 1e6)
    image_tolerance_ns = int(config.image_tolerance_ms * 1e6)

    aligned_images = {
        camera_name: align_nearest_forward_fill(episode_ts, messages_by_topic.get(topic, []), image_tolerance_ns)
        for camera_name, topic in config.images.items()
    }
    interpolated_obs = {
        field_name: [_interpolate_source(episode_ts, messages_by_topic, src, sync_tolerance_ns) for src in sources]
        for field_name, sources in config.observation.items()
    }
    interpolated_action = [
        _interpolate_source(episode_ts, messages_by_topic, src, sync_tolerance_ns) for src in config.action
    ]

    for idx in range(len(episode_ts)):
        observations = _concat_sources_at(interpolated_obs, idx)
        if observations is None:
            continue
        action = _concat_action_at(interpolated_action, idx)
        if action is None:
            continue
        camera_images = _decode_images_at(aligned_images, idx)
        if camera_images is None:
            continue
        yield Frame(camera_images=camera_images, observations=observations, action=action, task=task)


def align_nearest_forward_fill(
    ref_timestamps: list[int],
    messages: list[TimestampedMessage],
    tolerance_ns: int,
) -> list[TimestampedMessage | None]:
    """For each reference timestamp pick the nearest message within tolerance.

    Falls back to the last matched message (forward-fill); None only until the
    first match.
    """
    if not messages:
        return [None] * len(ref_timestamps)

    source_ts = [m.timestamp_ns for m in messages]
    aligned: list[TimestampedMessage | None] = []
    last_matched: TimestampedMessage | None = None

    for ts in ref_timestamps:
        idx = bisect.bisect_left(source_ts, ts)
        best: TimestampedMessage | None = None
        best_diff = tolerance_ns + 1
        for candidate in (idx - 1, idx):
            if 0 <= candidate < len(source_ts):
                diff = abs(source_ts[candidate] - ts)
                if diff < best_diff:
                    best_diff = diff
                    best = messages[candidate]
        if best is not None and best_diff <= tolerance_ns:
            last_matched = best
            aligned.append(best)
        else:
            aligned.append(last_matched)
    return aligned


def _interpolate_source(
    ref_timestamps: list[int],
    messages_by_topic: dict[str, list[TimestampedMessage]],
    source: SourceConfig,
    tolerance_ns: int,
) -> list[NDArray[np.float64] | None]:
    messages = messages_by_topic.get(source.topic, [])
    if not messages:
        return [None] * len(ref_timestamps)
    source_data = [
        TimestampedValue(
            timestamp_ns=msg.timestamp_ns,
            value=extract_field_data(msg.decoded, source.field, source.indices),
        )
        for msg in messages
    ]
    return get_interpolator(source.interpolation).interpolate(ref_timestamps, source_data, tolerance_ns)


def _probe_sources(
    probe_messages: dict[str, list[TimestampedMessage]],
    field_name: str,
    sources: list[SourceConfig],
) -> tuple[int, list[str]]:
    total_dim = 0
    names: list[str] = []
    for src in sources:
        messages = probe_messages.get(src.topic) or []
        if not messages:
            raise ValueError(f"No messages for topic: {src.topic}")
        sample = extract_field_data(messages[0].decoded, src.field, src.indices)
        dim = len(sample)
        if src.names:
            names.extend(src.names)
        else:
            names.extend(f"{field_name}_{i}" for i in range(total_dim, total_dim + dim))
        total_dim += dim
    return total_dim, names


def _concat_sources_at(
    interpolated: dict[str, list[list[NDArray[np.float64] | None]]],
    idx: int,
) -> dict[str, NDArray[np.float64]] | None:
    observations: dict[str, NDArray[np.float64]] = {}
    for field_name, per_source in interpolated.items():
        arrays: list[NDArray[np.float64]] = []
        for values in per_source:
            value = values[idx]
            if value is None:
                return None
            arrays.append(value)
        observations[field_name] = np.concatenate(arrays) if len(arrays) > 1 else arrays[0]
    return observations


def _concat_action_at(
    interpolated_action: list[list[NDArray[np.float64] | None]],
    idx: int,
) -> NDArray[np.float64] | None:
    arrays: list[NDArray[np.float64]] = []
    for values in interpolated_action:
        value = values[idx]
        if value is None:
            return None
        arrays.append(value)
    if not arrays:
        return None
    return np.concatenate(arrays) if len(arrays) > 1 else arrays[0]


def _decode_images_at(
    aligned_images: dict[str, list[TimestampedMessage | None]],
    idx: int,
) -> dict[str, NDArray[np.uint8]] | None:
    camera_images: dict[str, NDArray[np.uint8]] = {}
    for camera_name, aligned in aligned_images.items():
        message = aligned[idx]
        if message is None:
            return None
        camera_images[camera_name] = decode_ros_image(message.decoded)
    return camera_images
