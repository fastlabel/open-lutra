"""Orchestrates a LeRobot export across multiple recordings.

Probes the first recording for feature shapes, then streams every recording's
frames through the converter into a single LeRobot v3.0 dataset. Each recording
contributes exactly one episode.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.features.lerobot_export import converter
from app.features.lerobot_export.validation import validate_recordings
from app.features.lerobot_export.writer import LeRobotV30Writer
from app.features.recordings.meta import read_recording_meta
from app.infra.mcap import find_mcap_files

if TYPE_CHECKING:
    from app.features.lerobot_export.models import ExportConfig

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Summary of a completed export."""

    output_dir: Path
    total_episodes: int
    total_frames: int
    skipped: list[str]


def run_export(
    source_dirs: list[Path],
    config: ExportConfig,
    output_dir: Path,
    on_progress: ProgressCallback | None = None,
) -> ExportResult:
    """Convert the given recording directories into one LeRobot v3.0 dataset.

    Args:
        source_dirs: Recording directories (each holding one `.mcap`).
        config: Mapping configuration.
        output_dir: Destination dataset root (created if absent).
        on_progress: Optional callback (step, current, total).

    Raises:
        ValueError: If no recordings are usable or the config references topics
            absent from the first recording.
    """

    def progress(step: str, current: int, total: int) -> None:
        if on_progress is not None:
            on_progress(step, current, total)

    usable = [(d, find_mcap_files(d)[0]) for d in source_dirs if find_mcap_files(d)]
    skipped = [d.name for d in source_dirs if not find_mcap_files(d)]
    for name in skipped:
        logger.warning("Skipping recording without MCAP: %s", name)
    if not usable:
        raise ValueError("No recordings with an MCAP file were found")

    # Fail fast if any recording's metadata.yaml lacks the config's topics.
    validate_recordings([d for d, _ in usable], config)

    all_topics = config.all_topics()
    image_topics = list(config.images.values())

    # Probe the first recording for feature shapes and (optionally) fps.
    progress("probe", 0, len(usable))
    probe_messages = converter.read_topic_messages(usable[0][1], all_topics)
    fps = config.fps if config.fps > 0 else converter.detect_fps(probe_messages, image_topics)
    spec = converter.probe_feature_spec(probe_messages, config)

    # Write into a sibling temp dir and rename on success, so a failed export
    # never leaves a partial dataset that blocks the name / lists as complete.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", suffix=".tmp", dir=output_dir.parent))
    writer = LeRobotV30Writer(work_dir, fps, config.robot_type, spec)
    writer.open()
    try:
        for index, (recording_dir, mcap_path) in enumerate(usable):
            progress("convert", index, len(usable))
            messages = probe_messages if index == 0 else converter.read_topic_messages(mcap_path, all_topics)
            _export_recording(writer, recording_dir, messages, config, fps)
        progress("finalize", len(usable), len(usable))
        writer.close()
    except BaseException:
        # Clean up without masking the original error (abort swallows encoder errors).
        writer.abort()
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    work_dir.rename(output_dir)
    return ExportResult(
        output_dir=output_dir,
        total_episodes=writer.total_episodes,
        total_frames=writer.total_frames,
        skipped=skipped,
    )


def _export_recording(
    writer: LeRobotV30Writer,
    recording_dir: Path,
    messages: dict[str, list[converter.TimestampedMessage]],
    config: ExportConfig,
    fps: int,
) -> None:
    ref_timestamps = converter.compute_ref_timestamps(messages, fps, config.time_range)
    if not ref_timestamps:
        logger.warning("Skipping %s: no overlapping time range", recording_dir.name)
        return

    task = _resolve_task(recording_dir)
    for frame in converter.iter_episode_frames(messages, config, ref_timestamps, task):
        writer.add_frame(frame)
    writer.end_episode()


def _resolve_task(recording_dir: Path) -> str:
    meta = read_recording_meta(recording_dir)
    if meta is not None and meta.task_name:
        return meta.task_name
    return recording_dir.name
