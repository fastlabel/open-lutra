"""Tests for the header.stamp extraction utilities."""

from types import SimpleNamespace

from app.shared.stamp import extract_stamp_ns, extract_stamp_sec


class TestExtractStampSec:
    """Tests for extract_stamp_sec."""

    def test_with_valid_header(self) -> None:
        """Returns seconds when header.stamp is present."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=100, nanosec=500_000_000)))
        assert extract_stamp_sec(msg) == 100.5

    def test_without_header(self) -> None:
        """Returns None when there is no header."""
        msg = SimpleNamespace(data=b"hello")
        assert extract_stamp_sec(msg) is None

    def test_without_stamp(self) -> None:
        """Returns None when header is present but stamp is missing."""
        msg = SimpleNamespace(header=SimpleNamespace())
        assert extract_stamp_sec(msg) is None

    def test_zero_stamp(self) -> None:
        """Returns 0.0 when sec=0 and nanosec=0."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0)))
        assert extract_stamp_sec(msg) == 0.0

    def test_nanosec_precision(self) -> None:
        """Verifies nanosecond precision."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=123_456_789)))
        result = extract_stamp_sec(msg)
        assert result is not None
        assert abs(result - 1.123456789) < 1e-9

    def test_missing_sec_or_nanosec_returns_none(self) -> None:
        """Returns None when sec or nanosec is absent from the stamp."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1)))
        assert extract_stamp_sec(msg) is None


class TestExtractStampNs:
    """Tests for extract_stamp_ns."""

    def test_with_valid_header(self) -> None:
        """Returns nanoseconds when header.stamp is present."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=100, nanosec=500_000_000)))
        assert extract_stamp_ns(msg) == 100_500_000_000

    def test_without_header(self) -> None:
        """Returns None when there is no header."""
        msg = SimpleNamespace(data=b"hello")
        assert extract_stamp_ns(msg) is None

    def test_zero(self) -> None:
        """Returns 0 when sec=0 and nanosec=0."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0)))
        assert extract_stamp_ns(msg) == 0

    def test_without_stamp(self) -> None:
        """Returns None when header is present but stamp is missing."""
        assert extract_stamp_ns(SimpleNamespace(header=SimpleNamespace())) is None

    def test_missing_sec_or_nanosec_returns_none(self) -> None:
        """Returns None when sec or nanosec is absent from the stamp."""
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(nanosec=5)))
        assert extract_stamp_ns(msg) is None
