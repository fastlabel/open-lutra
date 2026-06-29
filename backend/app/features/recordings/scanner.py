"""Output directory scanning and lightweight metadata.yaml parsing.

Pure filesystem logic, split out of router.py.
"""

import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# Import the constant directly (not via the package __init__) to avoid eagerly
# importing the export writer's pandas/numpy stack at recordings-scan time.
from app.features.lerobot_export.exports import EXPORTS_DIRNAME
from app.features.recordings.meta import RECORDING_META_FILENAME, read_recording_meta
from app.features.recordings.schemas import FileEntry
from app.features.upload.cache import CACHE_FILENAME as UPLOAD_STATE_FILENAME
from app.features.upload.cache import load_state as load_upload_state
from app.features.validation.cache import CACHE_FILENAME as VALIDATION_RESULT_FILENAME
from app.features.validation.cache import load_report as load_validation_report

logger = logging.getLogger(__name__)

# The bag metadata sidecar that `ros2 bag record` writes next to the .mcap segments
# (distinct from RECORDING_META_FILENAME / recording_meta.json, this app's own metadata file).
MCAP_METADATA_FILENAME = "metadata.yaml"
QUALITY_REPORT_FILENAME = "quality_report.json"


@dataclass(frozen=True)
class _ParsedBundle:
    """Memoized parse result of a recording folder's source files.

    Holds everything that requires reading/parsing a file (the expensive part).
    Size, mtime, and artifact flags are intentionally NOT stored here — they are
    recomputed from disk on every scan so file-size freshness is never lost.
    """

    topic_count: int | None
    recording_start_ns: int | None
    duration_ns: int | None
    message_count: int | None
    validation_overall_status: str | None
    upload_status: str | None
    task_name: str | None
    recording_config_name: str | None
    tags: tuple[str, ...]


# Source files whose parsed contents are memoized per folder. A change to any of
# them (mtime or size) flips the fingerprint and invalidates that folder's entry.
_SOURCE_FILENAMES: tuple[str, ...] = (
    MCAP_METADATA_FILENAME,
    RECORDING_META_FILENAME,
    VALIDATION_RESULT_FILENAME,
    UPLOAD_STATE_FILENAME,
)

# A per-folder cache-validity token: the (st_mtime_ns, st_size) of each source
# file, or None when the file is absent. The cached parse is reused only while
# this fingerprint is unchanged.
_SourceFingerprint = tuple[tuple[int, int] | None, ...]

# Per-folder cache of parse results, keyed by absolute folder path and guarded by
# _cache_lock. Rebuilt and pruned to the folders present on every scan.
_parse_cache: dict[str, tuple[_SourceFingerprint, _ParsedBundle]] = {}
_cache_lock = threading.Lock()


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

    # Skip the reserved exports directory (generated datasets, not recordings).
    # Note: only this exact name is excluded — recording folders may legitimately
    # start with `_`/`.` (task names are unsanitized), and must stay visible.
    folders = [
        item
        for item in items
        if item.is_dir() and item.name != ".DS_Store" and item.name != EXPORTS_DIRNAME
    ]

    with _cache_lock:
        snapshot = dict(_parse_cache)

    fresh_cache: dict[str, tuple[_SourceFingerprint, _ParsedBundle]] = {}
    entries: list[FileEntry] = []
    for key, fingerprint, bundle, entry in _scan_folders(folders, output_dir, snapshot):
        fresh_cache[key] = (fingerprint, bundle)
        entries.append(entry)

    # Replace the cache wholesale so deleted / renamed folders are pruned.
    with _cache_lock:
        _parse_cache.clear()
        _parse_cache.update(fresh_cache)

    # Sort by recording_start_ns primarily, mtime as fallback. Descending (newest first).
    entries.sort(key=_sort_key_recording_desc, reverse=True)
    return entries


def _scan_folders(
    folders: list[Path],
    rel_root: Path,
    snapshot: dict[str, tuple[_SourceFingerprint, _ParsedBundle]],
) -> list[tuple[str, _SourceFingerprint, _ParsedBundle, FileEntry]]:
    """Build entries for every folder concurrently (I/O-bound). None results are dropped.

    Each worker reads the shared `snapshot` read-only and never mutates the cache,
    so no locking is needed inside the workers.
    """
    if not folders:
        return []
    workers = min(32, (os.cpu_count() or 4) * 4)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        built = executor.map(lambda folder: _build_recording_entry(folder, rel_root, snapshot), folders)
        return [result for result in built if result is not None]


def _build_recording_entry(
    folder: Path,
    rel_root: Path,
    cache_snapshot: dict[str, tuple[_SourceFingerprint, _ParsedBundle]],
) -> tuple[str, _SourceFingerprint, _ParsedBundle, FileEntry] | None:
    """Build a FileEntry (plus its cache payload) for a single recording folder.

    Returns None if no `.mcap` is present or the folder cannot be read. Size,
    mtime, and artifact flags are recomputed from a single `os.scandir` pass
    every call; only the parsed source-file contents are reused from the cache
    when their (mtime, size) fingerprint is unchanged.
    """
    total_size = 0
    has_mcap = False
    has_quality_report = False
    source_stats: dict[str, tuple[int, int]] = {}

    try:
        with os.scandir(folder) as children:
            for child in children:
                if not child.is_file():
                    continue
                try:
                    info = child.stat()
                except OSError as e:
                    logger.debug("Failed to read file size: %s - %s", child.path, e)
                    continue
                total_size += info.st_size
                name = child.name
                if name.endswith(".mcap"):
                    has_mcap = True
                elif name == QUALITY_REPORT_FILENAME:
                    has_quality_report = True
                if name in _SOURCE_FILENAMES:
                    source_stats[name] = (info.st_mtime_ns, info.st_size)
    except OSError:
        return None

    # Folders without any .mcap are not treated as recordings.
    if not has_mcap:
        return None

    fingerprint: _SourceFingerprint = tuple(source_stats.get(name) for name in _SOURCE_FILENAMES)
    key = str(folder)
    cached = cache_snapshot.get(key)
    bundle = cached[1] if cached is not None and cached[0] == fingerprint else _parse_sources(folder)

    entry = FileEntry(
        name=folder.name,
        path=str(folder.relative_to(rel_root)),
        size=total_size,
        modified_at=folder.stat().st_mtime,
        topic_count=bundle.topic_count,
        recording_start_ns=bundle.recording_start_ns,
        duration_ns=bundle.duration_ns,
        message_count=bundle.message_count,
        has_quality_report=has_quality_report,
        validation_overall_status=bundle.validation_overall_status,
        upload_status=bundle.upload_status,
        task_name=bundle.task_name,
        recording_config_name=bundle.recording_config_name,
        tags=list(bundle.tags),
    )
    return key, fingerprint, bundle, entry


def _parse_sources(folder: Path) -> _ParsedBundle:
    """Read and parse the four per-folder source files (the expensive, cached part)."""
    topic_count, start_ns, dur_ns, msg_count = read_metadata_summary(folder)
    meta = read_recording_meta(folder)
    validation_report = load_validation_report(folder)
    upload_state = load_upload_state(folder)
    return _ParsedBundle(
        topic_count=topic_count,
        recording_start_ns=start_ns,
        duration_ns=dur_ns,
        message_count=msg_count,
        validation_overall_status=validation_report.overall_status if validation_report else None,
        upload_status=upload_state.status if upload_state else None,
        task_name=meta.task_name if meta else None,
        recording_config_name=meta.recording_config_name if meta else None,
        tags=tuple(meta.tags) if meta else (),
    )


def _reset_cache() -> None:
    """Empty the parse cache. Used by tests to keep runs deterministic."""
    with _cache_lock:
        _parse_cache.clear()


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
