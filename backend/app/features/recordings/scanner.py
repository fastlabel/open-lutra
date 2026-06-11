"""Output directory scanning and lightweight metadata.yaml parsing.

Pure filesystem logic, split out of router.py.
"""

import logging
import re
from pathlib import Path

from app.features.lerobot_export import EXPORTS_DIRNAME
from app.features.recordings.meta import read_recording_meta
from app.features.recordings.schemas import FileEntry
from app.features.validation.cache import load_report as load_validation_report

logger = logging.getLogger(__name__)


def scan_output_dir(output_dir: Path) -> list[FileEntry]:
    """List recording folders directly under output_dir.

    Assumptions:
        - Every subdirectory under output_dir is a recording folder (or a
          manually-added folder).
        - Recording folders contain a flat set of files with no nested
          structure.
        - Files directly under output_dir and folders without any `.mcap`
          file are ignored.

    Sort:
        1. recording_start_ns (starting_time from metadata.yaml; immutable)
        2. File mtime (fallback for older recordings that have no
           metadata.yaml)

       mtime is not used as the primary key: when later operations (e.g.
       quality analysis) add or update files inside an existing recording,
       it would be re-ranked as "newest" and break the UI's descending
       date-time order.
    """
    try:
        items = list(output_dir.iterdir())
    except PermissionError:
        return []

    entries: list[FileEntry] = []
    for item in items:
        # Skip the reserved exports directory (generated datasets, not recordings).
        # Note: only this exact name is excluded — recording folders may legitimately
        # start with `_`/`.` (task names are unsanitized), and must stay visible.
        if not item.is_dir() or item.name == ".DS_Store" or item.name == EXPORTS_DIRNAME:
            continue
        entry = _build_recording_entry(item, output_dir)
        if entry is not None:
            entries.append(entry)

    # Sort by recording_start_ns primarily, mtime as fallback. Descending (newest first).
    entries.sort(key=_sort_key_recording_desc, reverse=True)
    return entries


def _build_recording_entry(folder: Path, rel_root: Path) -> FileEntry | None:
    """Build a FileEntry for a single recording folder. Returns None if no `.mcap` is present."""
    total_size = 0
    has_mcap = False
    has_quality_report = False

    try:
        children = list(folder.iterdir())
    except PermissionError:
        return None

    for child in children:
        if not child.is_file():
            continue
        try:
            total_size += child.stat().st_size
        except OSError as e:
            logger.debug("Failed to read file size: %s - %s", child, e)

        name = child.name
        if name.endswith(".mcap"):
            has_mcap = True
        elif name == "quality_report.json":
            has_quality_report = True

    # Folders without any .mcap are not treated as recordings.
    if not has_mcap:
        return None

    topic_count, start_ns, dur_ns, msg_count = read_metadata_summary(folder)
    meta = read_recording_meta(folder)
    validation_report = load_validation_report(folder)
    return FileEntry(
        name=folder.name,
        path=str(folder.relative_to(rel_root)),
        size=total_size,
        modified_at=folder.stat().st_mtime,
        topic_count=topic_count,
        recording_start_ns=start_ns,
        duration_ns=dur_ns,
        message_count=msg_count,
        has_quality_report=has_quality_report,
        validation_overall_status=(validation_report.overall_status if validation_report else None),
        task_name=meta.task_name if meta else None,
        robot_config_name=meta.robot_config_name if meta else None,
        tags=meta.tags if meta else [],
    )


def _sort_key_recording_desc(entry: FileEntry) -> tuple[int, float]:
    """Sort key that prioritizes recording start time.

    Element 1: recording_start_ns (recording start time in ns). 0 if missing.
    Element 2: modified_at (mtime) as fallback.

    When the first element ties (e.g. both lack metadata, or share the same
    timestamp), tuple comparison falls through to the second element.
    """
    return (entry.recording_start_ns or 0, entry.modified_at)


def collect_recent_task_names(output_dir: Path) -> list[str]:
    """Collect non-empty task_name values from every recording, deduped and
    ordered by most-recently-used (folder mtime descending).

    The result powers autocomplete on the recording-start form. Empty
    strings and missing/unreadable `recording_meta.json` files are skipped
    silently — they are not errors.
    """
    if not output_dir.is_dir():
        return []

    try:
        items = list(output_dir.iterdir())
    except PermissionError:
        return []

    # Capture (mtime, task_name) for every recording that has a meta entry.
    # OSError on any single folder (stat / is_dir / etc.) is logged and skipped.
    # On Python 3.10 `Path.is_dir()` itself calls `stat()`, so the guard must
    # cover both calls to be portable across versions.
    candidates: list[tuple[float, str]] = []
    for item in items:
        try:
            if not item.is_dir() or item.name == ".DS_Store" or item.name == EXPORTS_DIRNAME:
                continue

            meta = read_recording_meta(item)
            if meta is None or not meta.task_name:
                continue

            mtime = item.stat().st_mtime
        except OSError as e:
            logger.debug("Failed to inspect recording folder: %s - %s", item, e)
            continue

        candidates.append((mtime, meta.task_name))

    # Newest first. Then dedupe while preserving the order of first appearance
    # so the most recent occurrence wins.
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    seen: set[str] = set()
    unique: list[str] = []
    for _, name in candidates:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return unique


def read_metadata_summary(
    directory: Path,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Read topic count, start time, duration, and total message count from metadata.yaml (lightweight parse).

    Returns:
        (topic_count, recording_start_ns, duration_ns, message_count)
    """
    meta = directory / "metadata.yaml"
    if not meta.exists():
        return None, None, None, None
    try:
        text = meta.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Failed to read metadata.yaml (%s): %s", meta, e)
        return None, None, None, None

    topic_count = text.count("- topic_metadata:") or None

    # Capture only top-level starting_time / duration / message_count (exclude entries under files:).
    # Only look at the portion before the files: section.
    files_pos = text.find("\n  files:")
    header = text[:files_pos] if files_pos > 0 else text

    start_match = re.search(r"starting_time:\s*\n\s*nanoseconds_since_epoch:\s*(\d+)", header)
    dur_match = re.search(r"duration:\s*\n\s*nanoseconds:\s*(\d+)", header)
    # Match only the top-level message_count (indented with 2 spaces).
    # Nested values under topics_with_message_count are excluded because their indent is deeper.
    msg_match = re.search(r"^  message_count:\s*(\d+)", header, re.MULTILINE)

    start_ns = int(start_match.group(1)) if start_match else None
    dur_ns = int(dur_match.group(1)) if dur_match else None
    msg_count = int(msg_match.group(1)) if msg_match else None

    return topic_count, start_ns, dur_ns, msg_count
