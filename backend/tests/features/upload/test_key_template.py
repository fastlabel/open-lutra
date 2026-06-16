"""Tests for the destination key template renderer."""

from datetime import datetime, timezone

import pytest

from app.features.upload.key_template import KeyTemplateError, render_key, validate_template


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


class TestValidateTemplate:
    def test_accepts_known_placeholders(self) -> None:
        validate_template("prefix/{yyyymmddhhmmss}/{recording_name}.zip")

    def test_accepts_template_with_no_placeholders(self) -> None:
        validate_template("static/prefix/file.zip")

    def test_rejects_unknown_placeholder(self) -> None:
        with pytest.raises(KeyTemplateError, match="Unknown placeholder"):
            validate_template("prefix/{unknown}/file.zip")

    def test_rejects_task_name_placeholder(self) -> None:
        """`task_name` is intentionally not supported."""
        with pytest.raises(KeyTemplateError, match="Unknown placeholder"):
            validate_template("prefix/{task_name}/file.zip")

    def test_rejects_unbalanced_braces(self) -> None:
        with pytest.raises(KeyTemplateError, match="Unbalanced braces"):
            validate_template("prefix/{recording_name/file.zip")


class TestRenderKey:
    def test_substitutes_all_placeholders(self) -> None:
        ns = _ns(datetime(2026, 6, 8, 12, 34, 56, tzinfo=timezone.utc))
        key = render_key(
            "lutra/{yyyymmddhhmmss}/{recording_name}.zip",
            recording_name="rec_001",
            recording_start_ns=ns,
        )
        assert key == "lutra/20260608123456/rec_001.zip"

    def test_timestamp_is_utc(self) -> None:
        """yyyymmddhhmmss is in UTC regardless of process timezone."""
        ns = _ns(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        key = render_key(
            "{yyyymmddhhmmss}",
            recording_name="r",
            recording_start_ns=ns,
        )
        assert key == "20260101000000"

    def test_repeated_placeholder(self) -> None:
        ns = _ns(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        key = render_key(
            "{recording_name}/{recording_name}.zip",
            recording_name="r",
            recording_start_ns=ns,
        )
        assert key == "r/r.zip"

    def test_raises_on_invalid_template(self) -> None:
        with pytest.raises(KeyTemplateError):
            render_key(
                "prefix/{bad}/file.zip",
                recording_name="r",
                recording_start_ns=0,
            )
