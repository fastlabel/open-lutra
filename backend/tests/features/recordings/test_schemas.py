"""Tests for the recordings/schemas module.

Verifies the request-level validation of BulkUpdateMetaRequest and RecordingsQuery.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.features.recordings.schemas import BulkUpdateMetaRequest, RecordingsQuery


class TestBulkUpdateMetaRequest:
    """Tests for BulkUpdateMetaRequest."""

    def test_rejects_request_with_nothing_to_update(self) -> None:
        """A request that mentions neither metadata nor tags is refused instead of rewriting files."""
        with pytest.raises(ValidationError, match="Nothing to update"):
            BulkUpdateMetaRequest(folders=["rec_001"])

    def test_rejects_tag_in_both_add_and_remove(self) -> None:
        """The same tag cannot be added and removed in one request."""
        with pytest.raises(ValidationError, match=r"both added and removed: \['retry'\]"):
            BulkUpdateMetaRequest(folders=["rec_001"], add_tags=["retry", "good"], remove_tags=["retry"])

    @pytest.mark.parametrize(
        "fields",
        [
            {"metadata": {"target_object": "cup"}},
            {"add_tags": ["reviewed"]},
            {"remove_tags": ["retry"]},
        ],
    )
    def test_accepts_any_single_change(self, fields: dict[str, object]) -> None:
        """Metadata alone, add_tags alone, or remove_tags alone is a valid request; the rest default to empty."""
        req = BulkUpdateMetaRequest(folders=["rec_001"], **fields)

        assert req.metadata == fields.get("metadata", {})
        assert req.add_tags == fields.get("add_tags", [])
        assert req.remove_tags == fields.get("remove_tags", [])


class TestRecordingsQuery:
    """Tests for RecordingsQuery."""

    def test_parses_rfc3339_with_offset(self) -> None:
        """Bounds are parsed from RFC 3339 strings and keep their UTC offset."""
        query = RecordingsQuery.model_validate(
            {"started_after": "2026-11-04T00:00:00+09:00", "started_before": "2026-11-04T12:00:00+09:00"}
        )

        assert query.started_after == datetime(2026, 11, 4, tzinfo=timezone(timedelta(hours=9)))
        assert query.started_before == datetime(2026, 11, 4, 12, tzinfo=timezone(timedelta(hours=9)))

    def test_bounds_are_optional(self) -> None:
        """Omitting both bounds is valid and means no filtering."""
        query = RecordingsQuery()

        assert query.started_after is None
        assert query.started_before is None

    def test_rejects_value_without_offset(self) -> None:
        """A timezone-less value is refused rather than silently assumed to be UTC."""
        with pytest.raises(ValidationError, match="timezone"):
            RecordingsQuery.model_validate({"started_after": "2026-11-04T00:00:00"})

    @pytest.mark.parametrize("before", ["2026-11-04T00:00:00+09:00", "2026-11-03T23:00:00+09:00"])
    def test_rejects_empty_or_inverted_interval(self, before: str) -> None:
        """started_after must be strictly earlier than started_before."""
        with pytest.raises(ValidationError, match="started_after must be earlier than started_before"):
            RecordingsQuery.model_validate({"started_after": "2026-11-04T00:00:00+09:00", "started_before": before})
