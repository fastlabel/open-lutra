"""Bundle a recording folder into a single zip file.

The zip is written to `<recording_dir>/<recording_dir.name>.zip` and persisted
after upload — re-running the upload skips re-zipping when the inputs have not
changed (the zip is regenerated whenever any source file's mtime is newer than
the zip's, to handle artifacts produced after a previous zip).
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_COMPRESSION_LEVEL = 6  # zipfile default for ZIP_DEFLATED


def build_zip(recording_dir: Path) -> Path:
    """Zip every file directly inside `recording_dir` into `<dir>/<dir.name>.zip`.

    The zip itself is skipped during enumeration so re-runs are idempotent.
    Returns the zip path.
    """
    zip_path = recording_dir / f"{recording_dir.name}.zip"

    members = _collect_members(recording_dir, zip_path)
    if _zip_is_fresh(zip_path, members):
        logger.info("Zip is up to date, skipping rebuild: %s", zip_path)
        return zip_path

    # Write atomically: build a temp zip, then rename. Prevents leaving a
    # half-written zip if the process is killed mid-write.
    tmp_path = zip_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(
        tmp_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=_COMPRESSION_LEVEL,
    ) as zf:
        for member in members:
            zf.write(member, arcname=member.name)
    tmp_path.replace(zip_path)
    logger.info("Built zip: %s (%d files)", zip_path, len(members))
    return zip_path


def _collect_members(recording_dir: Path, zip_path: Path) -> list[Path]:
    """Return files directly inside `recording_dir`, excluding the zip itself."""
    members: list[Path] = []
    for entry in sorted(recording_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry == zip_path or entry.name.endswith(".zip.tmp"):
            continue
        members.append(entry)
    return members


def _zip_is_fresh(zip_path: Path, members: list[Path]) -> bool:
    """True when the zip exists and is newer than every member."""
    if not zip_path.exists():
        return False
    zip_mtime = zip_path.stat().st_mtime
    return all(m.stat().st_mtime <= zip_mtime for m in members)
