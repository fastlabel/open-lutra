"""Tests for the MCAP reader's user-facing error translation."""

from pathlib import Path

from mcap.exceptions import McapError

from app.infra.mcap import CorruptedMCAPError


class TestCorruptedMCAPError:
    """Tests for CorruptedMCAPError.from_cause()."""

    def test_names_file_cause_and_typical_reasons(self) -> None:
        cause = McapError("unknown (opcode 173) record has length 999 that exceeds limit")
        err = CorruptedMCAPError.from_cause(Path("/data/output/rec/rec_0.mcap"), cause)
        message = str(err)
        assert "rec_0.mcap" in message
        assert "exceeds limit" in message
        assert "truncated or corrupted" in message
        assert "recording was cut short" in message
        assert "disk filled up" in message

    def test_falls_back_to_class_name_for_empty_cause(self) -> None:
        err = CorruptedMCAPError.from_cause(Path("rec_0.mcap"), McapError())
        assert "McapError" in str(err)
