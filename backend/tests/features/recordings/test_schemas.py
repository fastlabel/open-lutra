"""Tests for the recordings/schemas module.

Verifies the request-level validation of BulkUpdateMetaRequest.
"""

import pytest
from pydantic import ValidationError

from app.features.recordings.schemas import BulkUpdateMetaRequest


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
