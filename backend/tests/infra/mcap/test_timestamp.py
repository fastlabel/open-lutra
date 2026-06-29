"""Tests for header.stamp-preferred timestamp normalization."""

from types import SimpleNamespace

from app.infra.mcap.timestamp import resolve_timestamp_ns, resolve_timestamp_sec


def _msg_with_stamp(sec: int, nanosec: int) -> SimpleNamespace:
    return SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=sec, nanosec=nanosec)))


_NO_HEADER = SimpleNamespace(data=b"x")


class TestResolveTimestampSec:
    def test_prefers_header_stamp(self) -> None:
        assert resolve_timestamp_sec(_msg_with_stamp(100, 500_000_000), log_time_ns=1) == 100.5

    def test_falls_back_to_log_time_without_header(self) -> None:
        assert resolve_timestamp_sec(_NO_HEADER, log_time_ns=2_000_000_000) == 2.0

    def test_falls_back_when_stamp_is_zero(self) -> None:
        assert resolve_timestamp_sec(_msg_with_stamp(0, 0), log_time_ns=3_000_000_000) == 3.0


class TestResolveTimestampNs:
    def test_prefers_header_stamp(self) -> None:
        assert resolve_timestamp_ns(_msg_with_stamp(100, 500_000_000), log_time_ns=1) == 100_500_000_000

    def test_falls_back_to_log_time_without_header(self) -> None:
        assert resolve_timestamp_ns(_NO_HEADER, log_time_ns=42) == 42

    def test_falls_back_when_stamp_is_zero(self) -> None:
        assert resolve_timestamp_ns(_msg_with_stamp(0, 0), log_time_ns=7) == 7
