"""Tests for the recording-folder zip builder."""

import os
import zipfile
from pathlib import Path

from app.features.upload.zip_builder import build_zip


def _populate(folder: Path) -> None:
    (folder / "data.mcap").write_bytes(b"binary-data")
    (folder / "metadata.yaml").write_text("starting_time:\n  nanoseconds_since_epoch: 0\n", encoding="utf-8")
    (folder / "recording_meta.json").write_text('{"task_name": "x"}', encoding="utf-8")


class TestBuildZip:
    def test_creates_zip_with_all_files(self, tmp_path: Path) -> None:
        rec = tmp_path / "rec_001"
        rec.mkdir()
        _populate(rec)

        zip_path = build_zip(rec)
        assert zip_path == rec / "rec_001.zip"
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = sorted(zf.namelist())
        assert names == ["data.mcap", "metadata.yaml", "recording_meta.json"]

    def test_excludes_zip_itself(self, tmp_path: Path) -> None:
        """A previously-built zip in the folder is not bundled into the new zip."""
        rec = tmp_path / "rec_001"
        rec.mkdir()
        _populate(rec)
        zip_path = build_zip(rec)
        # Force the zip's mtime to be older than the sources so we trigger a rebuild.
        old = zip_path.stat().st_mtime - 100
        os.utime(zip_path, (old, old))

        zip_path = build_zip(rec)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert "rec_001.zip" not in names

    def test_skips_rebuild_when_fresh(self, tmp_path: Path) -> None:
        """If the zip is newer than every source file, build_zip is a no-op."""
        rec = tmp_path / "rec_001"
        rec.mkdir()
        _populate(rec)

        zip_path = build_zip(rec)
        # Bump zip mtime far into the future so it is fresher than sources.
        future = zip_path.stat().st_mtime + 100
        os.utime(zip_path, (future, future))
        mtime_before = zip_path.stat().st_mtime

        rebuilt = build_zip(rec)
        assert rebuilt == zip_path
        assert zip_path.stat().st_mtime == mtime_before  # unchanged

    def test_rebuilds_when_source_changed(self, tmp_path: Path) -> None:
        """Updating a source file's content (with newer mtime) triggers a rebuild."""
        rec = tmp_path / "rec_001"
        rec.mkdir()
        _populate(rec)

        zip_path = build_zip(rec)
        old_zip_mtime = zip_path.stat().st_mtime

        # Replace content and force a newer mtime on the source.
        (rec / "data.mcap").write_bytes(b"updated-payload")
        future = old_zip_mtime + 100
        os.utime(rec / "data.mcap", (future, future))

        rebuilt = build_zip(rec)
        with zipfile.ZipFile(rebuilt) as zf:
            assert zf.read("data.mcap") == b"updated-payload"

    def test_ignores_subdirectories(self, tmp_path: Path) -> None:
        """Only files directly inside the recording folder are zipped."""
        rec = tmp_path / "rec_001"
        rec.mkdir()
        (rec / "a.mcap").write_bytes(b"x")
        sub = rec / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("y", encoding="utf-8")

        zip_path = build_zip(rec)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert names == ["a.mcap"]

    def test_ignores_temp_zip(self, tmp_path: Path) -> None:
        """A stale .zip.tmp from a crashed run is not bundled."""
        rec = tmp_path / "rec_001"
        rec.mkdir()
        (rec / "data.mcap").write_bytes(b"x")
        (rec / "rec_001.zip.tmp").write_bytes(b"stale")

        zip_path = build_zip(rec)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert "rec_001.zip.tmp" not in names
