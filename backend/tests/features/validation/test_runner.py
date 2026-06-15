"""Tests for ValidationRunner."""

from pathlib import Path
from typing import ClassVar

import pytest

from app.features.recordings.meta import RecordingMeta
from app.features.validation import (
    RecordingValidator,
    ValidationContext,
    ValidationResult,
    register_validator,
)
from app.features.validation.runner import ValidationRunner
from tests.features.validation.conftest import make_report


class _PassingValidator(RecordingValidator):
    name: ClassVar[str] = "passing"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        return ValidationResult(status="pass", message="ok")


class _FailingValidator(RecordingValidator):
    name: ClassVar[str] = "failing"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        return ValidationResult(status="fail", message="bad")


class _RaisingValidator(RecordingValidator):
    name: ClassVar[str] = "raising"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        raise RuntimeError("boom")


class _CtxInspectingValidator(RecordingValidator):
    """Captures the ctx passed by the runner for assertion."""

    name: ClassVar[str] = "ctx_inspector"
    last_ctx: ClassVar[ValidationContext | None] = None

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        type(self).last_ctx = ctx
        return ValidationResult(status="pass", message="seen")


def _run(
    *,
    recording_dir: Path | None = None,
    mcap_path: Path | None = None,
    recording_meta: RecordingMeta | None = None,
) -> ValidationRunner:
    return ValidationRunner()


def _invoke(
    runner: ValidationRunner,
    *,
    recording_dir: Path | None = None,
    mcap_path: Path | None = None,
    recording_meta: RecordingMeta | None = None,
):
    return runner.run(
        make_report(),
        recording_dir=recording_dir or Path("/tmp/recording"),
        mcap_path=mcap_path,
        recording_meta=recording_meta,
    )


@pytest.fixture
def _no_builtins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable builtin validators so the test only exercises customs."""
    monkeypatch.setattr(
        "app.features.validation.runner.get_builtin_recording_validators",
        lambda: [],
    )


class TestValidationRunner:
    """Tests for ValidationRunner.run()."""

    def test_empty_runner_returns_pass(self, _no_builtins: None) -> None:
        """With zero validators, overall_status is pass."""
        report = _invoke(_run())
        assert report.overall_status == "pass"
        assert report.results == []
        assert report.task_name is None

    def test_custom_pass(self, _no_builtins: None) -> None:
        register_validator(_PassingValidator)
        report = _invoke(
            _run(),
            recording_meta=RecordingMeta(task_name="t1"),
        )

        assert report.overall_status == "pass"
        assert report.task_name == "t1"
        assert len(report.results) == 1
        assert report.results[0].source == "custom"
        assert report.results[0].source_module is not None
        assert "tests.features.validation.test_runner" in report.results[0].source_module

    def test_custom_fail(self, _no_builtins: None) -> None:
        register_validator(_FailingValidator)
        report = _invoke(_run())
        assert report.overall_status == "fail"

    def test_exception_becomes_error_status(self, _no_builtins: None) -> None:
        """A validator that raises produces a result with status="error"."""
        register_validator(_RaisingValidator)
        report = _invoke(_run())

        assert report.overall_status == "error"
        assert len(report.results) == 1
        assert report.results[0].status == "error"
        assert "RuntimeError" in report.results[0].message
        assert "boom" in report.results[0].message

    def test_exception_does_not_stop_other_validators(self, _no_builtins: None) -> None:
        """One validator raising does not prevent the others from running."""
        register_validator(_RaisingValidator)
        register_validator(_PassingValidator)

        report = _invoke(_run())
        assert len(report.results) == 2
        statuses = {r.status for r in report.results}
        assert statuses == {"error", "pass"}
        assert report.overall_status == "error"

    def test_default_builtins_run_when_not_patched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The runner invokes builtins from active_set by default."""
        from unittest.mock import MagicMock

        from app.settings import ValidatorEntry

        mock_s = MagicMock()
        mock_s.recording.validators = [
            ValidatorEntry(name="required_topics_present", topics=[]),
            ValidatorEntry(name="total_duration_sec"),
        ]
        monkeypatch.setattr("app.features.validation.active_set.get_settings", lambda: mock_s)

        report = _invoke(_run())
        assert all(r.source == "builtin" for r in report.results)
        assert {r.validator_name for r in report.results} == {
            "required_topics_present",
            "total_duration_sec",
        }
        assert report.overall_status == "pass"

    def test_ctx_carries_recording_dir_mcap_path_and_meta(self, _no_builtins: None) -> None:
        """Every field on the runner is forwarded into ValidationContext."""
        register_validator(_CtxInspectingValidator)
        meta = RecordingMeta(task_name="task-a", tags=["v1"])
        recording_dir = Path("/tmp/some/recording")
        mcap_path = recording_dir / "rec.mcap"

        _invoke(
            _run(),
            recording_dir=recording_dir,
            mcap_path=mcap_path,
            recording_meta=meta,
        )

        seen = _CtxInspectingValidator.last_ctx
        assert seen is not None
        assert seen.recording_dir == recording_dir
        assert seen.mcap_path == mcap_path
        assert seen.recording_meta == meta

    def test_ctx_allows_none_mcap_and_meta(self, _no_builtins: None) -> None:
        """When the MCAP file or recording_meta is missing, ctx exposes None."""
        register_validator(_CtxInspectingValidator)
        _invoke(_run(), mcap_path=None, recording_meta=None)

        seen = _CtxInspectingValidator.last_ctx
        assert seen is not None
        assert seen.mcap_path is None
        assert seen.recording_meta is None
