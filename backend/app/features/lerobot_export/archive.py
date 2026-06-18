"""Bundle an exported LeRobot dataset into a single zip for browser download.

A dataset is a directory tree (`meta/`, `data/`, `videos/`), so the archive
preserves the tree under a top-level `<name>/` prefix — it unpacks into its own
directory. Contents are already-compressed media (H.264 MP4) and parquet, so the
archive is stored uncompressed (`ZIP_STORED`): DEFLATE would burn CPU for a
negligible size reduction.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def build_export_zip(dataset_dir: Path, zip_path: Path) -> Path:
    """Zip every file under `dataset_dir` into `zip_path`, preserving the tree.

    Archive names are rooted at `<dataset_dir.name>/`. Returns the zip path.
    """
    members = sorted(p for p in dataset_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for member in members:
            arcname = Path(dataset_dir.name) / member.relative_to(dataset_dir)
            zf.write(member, arcname=str(arcname))
    return zip_path
