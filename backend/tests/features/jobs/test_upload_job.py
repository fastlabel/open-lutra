"""Tests for the upload-related parts of the JobQueue.

These cover only the upload-specific enqueue / discovery / runner paths.
The rest of JobQueue (media / quality / timeline / validation) keeps its
existing testing strategy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.jobs.models import JobStatus, JobType, UploadJob
from app.features.jobs.service import JobQueue
from app.features.upload.cache import load_state
from app.features.upload.destinations.base import UploadResult
from app.settings import Settings


def _make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "recording_config": "config/simulator.yaml",
        "output_dir": "/tmp",
        "s3_bucket": "lutra-test",
        "s3_key_template": "uploads/{recording_name}.zip",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _write_metadata_yaml(directory: Path, *, start_ns: int | None = 1_700_000_000_000_000_000) -> None:
    """Write a minimal metadata.yaml so `read_metadata_summary` returns a start time."""
    if start_ns is None:
        directory.joinpath("metadata.yaml").write_text("rosbag2_bagfile_information:\n", encoding="utf-8")
        return
    directory.joinpath("metadata.yaml").write_text(
        "rosbag2_bagfile_information:\n"
        f"  starting_time:\n    nanoseconds_since_epoch: {start_ns}\n"
        "  duration:\n    nanoseconds: 1000000000\n"
        "  message_count: 0\n",
        encoding="utf-8",
    )


def _seed_recording(directory: Path) -> None:
    """Put a couple of files in the folder so `build_zip` produces a non-empty archive."""
    (directory / "rec_0.mcap").write_bytes(b"\x00" * 16)
    (directory / "metadata.yaml")  # caller writes this separately


class TestEnqueueUpload:
    async def test_enqueue_creates_active_job(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_upload(tmp_path)

        assert isinstance(job, UploadJob)
        assert job.type == JobType.UPLOAD
        assert job.target_path == tmp_path
        assert job.folder == tmp_path.name
        assert job.status == JobStatus.QUEUED
        assert job.job_id.startswith("upl_")

        active = queue.get_active_upload_job(tmp_path)
        assert active is not None
        assert active.job_id == job.job_id

    async def test_enqueue_is_idempotent(self, tmp_path: Path) -> None:
        """Re-enqueueing the same folder returns the existing job."""
        queue = JobQueue()
        first = await queue.enqueue_upload(tmp_path)
        second = await queue.enqueue_upload(tmp_path)

        assert first.job_id == second.job_id

    async def test_get_active_returns_none_when_no_job(self, tmp_path: Path) -> None:
        queue = JobQueue()
        assert queue.get_active_upload_job(tmp_path) is None


class TestRunUpload:
    """Direct invocation of JobQueue._run_upload()."""

    async def test_writes_uploaded_state_on_success(self, tmp_path: Path) -> None:
        """Happy path: zip + upload + final UploadState with etag persisted."""
        _seed_recording(tmp_path)
        _write_metadata_yaml(tmp_path)

        destination = MagicMock()
        destination.configuration_error.return_value = None
        destination.prepare_target.return_value = (
            "lutra-test",
            f"uploads/{tmp_path.name}.zip",
        )
        destination.upload.return_value = UploadResult(size_bytes=4096, etag='"abc-1"')

        queue = JobQueue()
        job = await queue.enqueue_upload(tmp_path)

        with (
            patch("app.settings.get_settings", return_value=_make_settings()),
            patch(
                "app.features.upload.destinations.get_active_destination",
                return_value=destination,
            ),
        ):
            await queue._run_upload(job)

        destination.upload.assert_called_once()
        args = destination.upload.call_args.args
        assert args[0] == tmp_path / f"{tmp_path.name}.zip"
        # Key was rendered from the template (uploads/{recording_name}.zip).
        assert args[1] == f"uploads/{tmp_path.name}.zip"

        state = load_state(tmp_path)
        assert state is not None
        assert state.status == "uploaded"
        assert state.destination == "lutra-test"
        assert state.key == f"uploads/{tmp_path.name}.zip"
        assert state.etag == '"abc-1"'
        assert state.size_bytes == 4096
        assert state.bytes_transferred == 4096
        assert state.uploaded_at is not None
        assert state.uploaded_at <= datetime.now(timezone.utc)
        assert state.error is None

    async def test_writes_failed_state_on_exception(self, tmp_path: Path) -> None:
        """On upload failure, status flips to `failed` with the exception message."""
        _seed_recording(tmp_path)
        _write_metadata_yaml(tmp_path)

        destination = MagicMock()
        destination.configuration_error.return_value = None
        destination.prepare_target.return_value = (
            "lutra-test",
            f"uploads/{tmp_path.name}.zip",
        )
        destination.upload.side_effect = RuntimeError("network unreachable")

        queue = JobQueue()
        job = await queue.enqueue_upload(tmp_path)

        with (
            patch("app.settings.get_settings", return_value=_make_settings()),
            patch(
                "app.features.upload.destinations.get_active_destination",
                return_value=destination,
            ),
            pytest.raises(RuntimeError, match="network unreachable"),
        ):
            await queue._run_upload(job)

        state = load_state(tmp_path)
        assert state is not None
        assert state.status == "failed"
        assert state.error == "network unreachable"
        assert state.uploaded_at is None

    async def test_raises_when_destination_misconfigured(self, tmp_path: Path) -> None:
        """If `destination.configuration_error()` returns a string, fail fast."""
        _seed_recording(tmp_path)
        _write_metadata_yaml(tmp_path)

        destination = MagicMock()
        destination.configuration_error.return_value = "S3_BUCKET is not configured"

        queue = JobQueue()
        job = await queue.enqueue_upload(tmp_path)

        with (
            patch("app.settings.get_settings", return_value=_make_settings(s3_bucket=None)),
            patch(
                "app.features.upload.destinations.get_active_destination",
                return_value=destination,
            ),
            pytest.raises(RuntimeError, match="S3_BUCKET is not configured"),
        ):
            await queue._run_upload(job)

        destination.upload.assert_not_called()
        # No state file written when the precondition fails before zip creation.
        assert load_state(tmp_path) is None

    async def test_raises_when_metadata_missing_start_time(self, tmp_path: Path) -> None:
        """Key rendering requires recording_start_ns; fail if metadata.yaml does not carry it."""
        _seed_recording(tmp_path)
        _write_metadata_yaml(tmp_path, start_ns=None)

        destination = MagicMock()
        destination.configuration_error.return_value = None
        destination.prepare_target.return_value = (
            "lutra-test",
            f"uploads/{tmp_path.name}.zip",
        )

        queue = JobQueue()
        job = await queue.enqueue_upload(tmp_path)

        with (
            patch("app.settings.get_settings", return_value=_make_settings()),
            patch(
                "app.features.upload.destinations.get_active_destination",
                return_value=destination,
            ),
            pytest.raises(FileNotFoundError, match=r"metadata\.yaml"),
        ):
            await queue._run_upload(job)

        destination.upload.assert_not_called()
        assert load_state(tmp_path) is None

    async def test_progress_callback_persists_intermediate_state(self, tmp_path: Path) -> None:
        """The throttled progress callback updates `bytes_transferred` in upload_state.json."""
        _seed_recording(tmp_path)
        _write_metadata_yaml(tmp_path)

        destination = MagicMock()
        destination.configuration_error.return_value = None
        destination.prepare_target.return_value = (
            "lutra-test",
            f"uploads/{tmp_path.name}.zip",
        )

        def fake_upload(local_path: Path, key: str, progress: object) -> UploadResult:
            # Simulate boto3 invoking the callback with byte-deltas.
            assert callable(progress)
            progress(2048)
            progress.close()  # type: ignore[attr-defined]
            return UploadResult(size_bytes=2048, etag='"final"')

        destination.upload.side_effect = fake_upload

        queue = JobQueue()
        job = await queue.enqueue_upload(tmp_path)

        with (
            patch("app.settings.get_settings", return_value=_make_settings()),
            patch(
                "app.features.upload.destinations.get_active_destination",
                return_value=destination,
            ),
        ):
            await queue._run_upload(job)

        state = load_state(tmp_path)
        assert state is not None
        assert state.status == "uploaded"
        assert state.bytes_transferred == 2048
