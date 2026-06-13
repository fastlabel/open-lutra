"""Conversion engine that generates MP4 video and telemetry.json from MCAP files.

Uses mcap-ros2-support for CDR deserialization and pipes CompressedImage to
ffmpeg to produce MP4. JointState data is resampled at a fixed FPS and written
to telemetry.json.

MP4 generation streams MCAP per camera to minimize memory usage
(only one frame held at a time, constant memory regardless of recording length).

All functions depend on MCAP I/O and ffmpeg subprocesses, so they are marked
pragma: no cover.
"""

import json
import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.features.media.models import (
    JointStateMapping,
    JointTopicEntry,
    MediaError,
    MissingTopicError,
    build_joint_state_mapping,
    derive_camera_name,
)
from app.infra.mcap import (
    MCAPReader,
    extract_joint_positions,
    find_mcap_files,
    is_image_message,
    resolve_timestamp_ns,
)

logger = logging.getLogger(__name__)


@dataclass
class _TimestampedMessage:
    """Decoded message with a timestamp."""

    timestamp_ns: int
    decoded: Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def convert_mcap(  # pragma: no cover
    mcap_dir: Path,
    output_dir: Path,
    fps: int,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> list[str]:
    """Generate MP4 and telemetry.json from an MCAP directory.

    Streams MCAP per camera and processes frame data one at a time, so
    memory usage stays constant regardless of recording length.

    Args:
        mcap_dir: Recording directory containing the MCAP files.
        output_dir: Output directory for MP4 and telemetry.json.
        fps: Fixed FPS for the output video and telemetry.
        on_progress: Progress callback (step, current, total).
            step: "classify" / "mp4" / "telemetry"

    Returns:
        List of generated file paths.

    Raises:
        FileNotFoundError: If no MCAP file is found.
        MissingTopicError: If required topics are missing.
    """
    mcap_path = _find_mcap_file(mcap_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def _progress(step: str, current: int, total: int) -> None:
        if on_progress:
            on_progress(step, current, total)

    # Automatically classify each MCAP topic as image / non-image (Joint-style)
    _progress("classify", 0, 1)
    image_topics, joint_topics = _classify_topics(mcap_path)

    if not image_topics and not joint_topics:
        raise MissingTopicError(f"No convertible topics found: {mcap_dir.name}")

    # Get the time range from actual message timestamps (preferring header.stamp).
    # The MCAP summary is log_time-based and can deviate significantly from header.stamp.
    first_ts, last_ts = _scan_time_range(mcap_path)
    interval_ns = int(1e9 / fps)
    frame_timestamps = list(range(first_ts, last_ts + 1, interval_ns))

    generated_files: list[str] = []

    try:
        # Generate MP4 (stream MCAP per camera)
        total_mp4 = len(image_topics)
        for mp4_idx, topic in enumerate(image_topics):
            _progress("mp4", mp4_idx, total_mp4)
            camera_name = derive_camera_name(topic)
            output_name = f"observation.images.{camera_name}.mp4"
            output_path = output_dir / output_name

            _stream_generate_mp4(
                mcap_path=mcap_path,
                topic=topic,
                frame_timestamps=frame_timestamps,
                fps=fps,
                output_path=output_path,
            )
            generated_files.append(output_name)
            logger.info("MP4 generation complete: %s (%d frames)", output_name, len(frame_timestamps))

        _progress("mp4", total_mp4, total_mp4)

        # Generate telemetry.json (Joint topics only; extract values only to save memory)
        _progress("telemetry", 0, 1)
        if joint_topics:
            mapping = build_joint_state_mapping(joint_topics)
            if mapping is not None:
                telemetry_path = output_dir / "telemetry.json"
                joint_data = _extract_joint_data(mcap_path, list(joint_topics))
                _generate_telemetry_from_data(
                    joint_data=joint_data,
                    mapping=mapping,
                    frame_timestamps=frame_timestamps,
                    fps=fps,
                    output_path=telemetry_path,
                )
                generated_files.append("telemetry.json")
                logger.info("telemetry.json generation complete: %d frames", len(frame_timestamps))
            else:
                logger.warning("Cannot build JointState mapping: %s (skipping telemetry.json)", mcap_dir.name)
        else:
            logger.info("No JointState topics: %s (skipping telemetry.json)", mcap_dir.name)

        return generated_files
    except Exception:
        # On failure, clean up generated files (do not leave an incomplete set)
        for name in generated_files:
            path = output_dir / name
            if path.exists():
                path.unlink()
                logger.info("Cleanup on failure: removed %s", name)
        raise


# ---------------------------------------------------------------------------
# Private: MCAP reading
# ---------------------------------------------------------------------------


def _find_mcap_file(directory: Path) -> Path:  # pragma: no cover
    """Return the first MCAP file in the directory."""
    mcap_files = find_mcap_files(directory)
    if not mcap_files:
        raise FileNotFoundError(f"MCAP file not found: {directory}")
    return mcap_files[0]


def _scan_time_range(mcap_path: Path) -> tuple[int, int]:  # pragma: no cover
    """Get the header.stamp-preferred timestamp range across all MCAP messages.

    The MCAP summary is log_time-based and can deviate from header.stamp
    (e.g., a camera's header.stamp is not NTP-synced and is off by hours).
    To get a unified time range across all topics, compute min/max in a
    single pass. No decoding is required because only the header is read,
    so it is fast.
    """
    min_ts: int | None = None
    max_ts: int | None = None

    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages():
            ts = resolve_timestamp_ns(msg.decoded, msg.timestamp_ns)
            if min_ts is None or ts < min_ts:
                min_ts = ts
            if max_ts is None or ts > max_ts:
                max_ts = ts

    if min_ts is None or max_ts is None:
        raise MissingTopicError(f"No messages: {mcap_path.name}")

    return min_ts, max_ts


def _classify_topics(mcap_path: Path) -> tuple[dict[str, str], dict[str, str]]:  # pragma: no cover
    """Automatically classify each MCAP topic as image / non-image (Joint-style).

    Decodes the first message of each topic and decides whether it is an image
    based on its structure. Non-image topics are treated as Joint-style.

    Returns:
        (image_topics, joint_topics): dict of topic name -> message type name
    """
    image_topics: dict[str, str] = {}
    joint_topics: dict[str, str] = {}
    seen: set[str] = set()

    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages():
            topic = msg.topic
            if topic in seen:
                continue
            seen.add(topic)

            if is_image_message(msg.decoded):
                image_topics[topic] = msg.msg_type
            else:
                joint_topics[topic] = msg.msg_type

    logger.info(
        "Topic classification: image=%s, joint=%s",
        list(image_topics.keys()),
        list(joint_topics.keys()),
    )
    return image_topics, joint_topics


# ---------------------------------------------------------------------------
# Private: MP4 generation (streaming)
# ---------------------------------------------------------------------------


def _stream_generate_mp4(
    mcap_path: Path,
    topic: str,
    frame_timestamps: list[int],
    fps: int,
    output_path: Path,
) -> None:  # pragma: no cover
    """Stream the given topic from MCAP and generate an MP4.

    Reads frames one at a time to minimize memory usage; the previous frame
    is overwritten immediately.
    Assigns the nearest frame via forward-fill against the fixed-FPS
    timestamp sequence.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "image2pipe",
        "-c:v",
        "mjpeg",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-loglevel",
        "warning",
        str(output_path),
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    try:
        if proc.stdin is None:
            raise MediaError("Cannot obtain stdin of the ffmpeg process")

        # Drain stderr in a separate thread to avoid deadlocks from pipe buffer overflow
        stderr_chunks: list[bytes] = []

        def _drain_stderr() -> None:
            if proc.stderr:
                stderr_chunks.append(proc.stderr.read())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # Stream from MCAP -> forward-fill -> pipe to ffmpeg
        with MCAPReader(mcap_path) as reader:
            msg_iter = reader.iter_messages(topics=[topic])

            # Closure that reads the next message into the buffer
            pending_ts: int | None = None
            pending_data: bytes | None = None

            def _advance() -> bool:
                """Read the next message. Returns False if no more messages."""
                nonlocal pending_ts, pending_data
                for m in msg_iter:
                    pending_ts = resolve_timestamp_ns(m.decoded, m.timestamp_ns)
                    pending_data = bytes(m.decoded.data)
                    return True
                pending_ts = None
                pending_data = None
                return False

            if not _advance():
                logger.warning("No image messages: %s (%s)", output_path.name, topic)
                proc.stdin.close()
                proc.wait(timeout=10)
                stderr_thread.join(timeout=5)
                if output_path.exists():
                    output_path.unlink()
                return

            # Initialize with the first frame (forward-fill: use the first frame before data arrives)
            current_data = pending_data
            _advance()

            for target_ts in frame_timestamps:
                # Advance to the latest message at or before target_ts
                while pending_ts is not None and pending_ts <= target_ts:
                    current_data = pending_data
                    _advance()

                proc.stdin.write(current_data)  # type: ignore[arg-type]

        proc.stdin.close()
        proc.wait(timeout=120)
        stderr_thread.join(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()
        # Remove incomplete MP4 on failure
        if output_path.exists():
            output_path.unlink()
            logger.info("ffmpeg failed: removed incomplete file: %s", output_path.name)
        raise

    stderr_bytes = b"".join(stderr_chunks)
    if proc.returncode != 0:
        # Also remove incomplete file on ffmpeg error
        if output_path.exists():
            output_path.unlink()
        raise MediaError(f"ffmpeg failed (code={proc.returncode}): {stderr_bytes.decode('utf-8', errors='replace')}")


@dataclass
class _JointTopicData:
    """Lightweight data extracted from a Joint topic (no decoded objects held)."""

    timestamps: list[int]
    positions: list[list[float]]
    joint_count: int  # Number of joints per message


def _extract_joint_data(
    mcap_path: Path,
    joint_topics: list[str],
) -> dict[str, _JointTopicData]:  # pragma: no cover
    """Extract only timestamps and position values for Joint topics from MCAP.

    Does not hold CDR-decoded objects; copies only the required values
    (timestamps and position arrays) as Python primitives. This drops the
    references to MCAP chunk buffers so GC can reclaim chunk memory immediately.
    """
    data: dict[str, _JointTopicData] = {
        t: _JointTopicData(timestamps=[], positions=[], joint_count=0) for t in joint_topics
    }
    topic_set = set(joint_topics)
    joint_count_captured: set[str] = set()

    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages(topics=joint_topics):
            topic = msg.topic
            if topic not in topic_set:
                continue

            ts = resolve_timestamp_ns(msg.decoded, msg.timestamp_ns)
            positions = extract_joint_positions(msg.decoded)

            data[topic].timestamps.append(ts)
            data[topic].positions.append(positions)

            if topic not in joint_count_captured and positions:
                data[topic].joint_count = len(positions)
                joint_count_captured.add(topic)
            # decoded is not retained -> eligible for GC

    return data


# ---------------------------------------------------------------------------
# Private: telemetry.json generation
# ---------------------------------------------------------------------------


def _sort_topic_data(
    topic_data: _JointTopicData,
) -> tuple[list[int], list[list[float]]]:
    """Sort by timestamp and return (timestamps, positions) pair."""
    if not topic_data.timestamps:
        return [], []
    order = sorted(range(len(topic_data.timestamps)), key=lambda i: topic_data.timestamps[i])
    timestamps = [topic_data.timestamps[i] for i in order]
    positions = [topic_data.positions[i] for i in order]
    return timestamps, positions


def _generate_telemetry_from_data(
    joint_data: dict[str, _JointTopicData],
    mapping: JointStateMapping,
    frame_timestamps: list[int],
    fps: int,
    output_path: Path,
) -> None:  # pragma: no cover
    """Generate telemetry.json from extracted Joint data.

    Combine data from multiple observation/action topics in a stable order
    and resample with nearest-neighbor interpolation against the fixed-FPS
    timestamp sequence.
    Joint names are generated from the topic names with the URDF prefix
    (R_, L_, "") prepended.
    """
    # --- Prepare observation side ---
    obs_sorted: list[tuple[JointTopicEntry, list[int], list[list[float]]]] = []
    for entry in mapping.observation_entries:
        topic_data = joint_data.get(entry.topic)
        if not topic_data or not topic_data.timestamps:
            logger.warning("No observation JointState messages: %s", entry.topic)
            continue
        timestamps, positions = _sort_topic_data(topic_data)
        obs_sorted.append((entry, timestamps, positions))

    if not obs_sorted:
        logger.warning("No valid observation JointState topics")
        return

    # --- Prepare action side ---
    act_sorted: list[tuple[JointTopicEntry, list[int], list[list[float]]]] = []
    for entry in mapping.action_entries:
        topic_data = joint_data.get(entry.topic)
        if not topic_data or not topic_data.timestamps:
            continue
        timestamps, positions = _sort_topic_data(topic_data)
        act_sorted.append((entry, timestamps, positions))

    # Fall back to observation if there is no action
    if not act_sorted:
        act_sorted = list(obs_sorted)

    # --- Generate joint names (prefix + JOINT_N) ---
    obs_joint_names: list[str] = []
    for entry, _, positions in obs_sorted:
        n = len(positions[0]) if positions else 0
        obs_joint_names.extend(f"{entry.joint_prefix}JOINT_{i + 1}" for i in range(n))

    act_joint_names: list[str] = []
    for entry, _, positions in act_sorted:
        n = len(positions[0]) if positions else 0
        act_joint_names.extend(f"{entry.joint_prefix}JOINT_{i + 1}" for i in range(n))

    # --- Resample per frame ---
    frames: list[dict[str, Any]] = []
    for i, target_ts in enumerate(frame_timestamps):
        obs_values: list[float] = []
        for _entry, timestamps, positions in obs_sorted:
            idx = _find_nearest_index(timestamps, target_ts)
            obs_values.extend(positions[idx])

        act_values: list[float] = []
        for _entry, timestamps, positions in act_sorted:
            idx = _find_nearest_index(timestamps, target_ts)
            act_values.extend(positions[idx])

        frame: dict[str, Any] = {
            "observation.state": obs_values,
            "action": act_values,
            "frame_index": i,
            "timestamp": i / fps,
        }

        if obs_joint_names:
            frame["observation.state.names"] = obs_joint_names
        if act_joint_names:
            frame["action.names"] = act_joint_names

        frames.append(frame)

    output_path.write_text(
        json.dumps(frames, ensure_ascii=False),
        encoding="utf-8",
    )


def _find_nearest_index(
    timestamps: list[int],
    target_ns: int,
) -> int:  # pragma: no cover
    """Return the latest index at or before target_ns from a sorted timestamp list (forward-fill).

    Uses bisect_right to search in O(log n).
    Returns 0 (the first element) if no element is at or before target_ns.
    """
    from bisect import bisect_right

    idx = bisect_right(timestamps, target_ns)
    return max(idx - 1, 0)
