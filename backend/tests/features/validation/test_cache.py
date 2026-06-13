"""Tests for validation_result.json load/save."""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.features.validation.cache import CACHE_FILENAME, load_report, save_report
from app.features.validation.models import ValidationReport, ValidationResultItem


def _make_report() -> ValidationReport:
    return ValidationReport(
        overall_status="warn",
        results=[
            ValidationResultItem(
                validator_name="dummy",
                source="builtin",
                source_module=None,
                status="warn",
                message="something",
                details={"key": "value"},
            ),
        ],
        task_name="my_task",
        executed_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestSaveLoad:
    def test_roundtrip(self, tmp_path: Path) -> None:
        original = _make_report()
        save_report(tmp_path, original)

        loaded = load_report(tmp_path)
        assert loaded is not None
        assert loaded.overall_status == "warn"
        assert loaded.task_name == "my_task"
        assert len(loaded.results) == 1
        assert loaded.results[0].validator_name == "dummy"
        assert loaded.results[0].details == {"key": "value"}

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        assert load_report(tmp_path) is None

    def test_load_corrupted_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / CACHE_FILENAME).write_text("{not valid json", encoding="utf-8")
        assert load_report(tmp_path) is None

    def test_load_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        """Valid JSON but a schema mismatch yields None."""
        (tmp_path / CACHE_FILENAME).write_text(json.dumps({"unexpected": "field"}), encoding="utf-8")
        assert load_report(tmp_path) is None
