"""Tests for bundling an exported dataset into a downloadable zip."""

import zipfile
from pathlib import Path

from app.features.lerobot_export.archive import build_export_zip


def test_build_export_zip_preserves_tree(tmp_path: Path) -> None:
    dataset = tmp_path / "ds_v1"
    (dataset / "meta").mkdir(parents=True)
    (dataset / "data" / "chunk-000").mkdir(parents=True)
    (dataset / "meta" / "info.json").write_text("{}")
    (dataset / "data" / "chunk-000" / "file-000.parquet").write_bytes(b"PAR1")

    zip_path = tmp_path / "out.zip"
    result = build_export_zip(dataset, zip_path)

    assert result == zip_path
    with zipfile.ZipFile(zip_path) as zf:
        # Archive names are rooted at the dataset name so it unpacks into its own dir.
        assert sorted(zf.namelist()) == [
            "ds_v1/data/chunk-000/file-000.parquet",
            "ds_v1/meta/info.json",
        ]
        # Stored uncompressed: contents are already-compressed media / parquet.
        assert all(info.compress_type == zipfile.ZIP_STORED for info in zf.infolist())
        assert zf.read("ds_v1/meta/info.json") == b"{}"


def test_build_export_zip_empty_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "empty"
    dataset.mkdir()
    zip_path = tmp_path / "out.zip"
    build_export_zip(dataset, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == []
