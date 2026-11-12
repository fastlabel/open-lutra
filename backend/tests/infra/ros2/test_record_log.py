"""Tests for forwarding ros2 bag record's console output to the logger."""

import logging

import pytest

from app.infra.ros2.record_log import RecordOutputLogger, describe_exit


def _records(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records]


@pytest.fixture(autouse=True)
def _capture_all(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="app.infra.ros2.record_log")


class TestDescribeExit:
    @pytest.mark.parametrize(
        ("returncode", "expected"),
        [
            (0, "exit code=0"),
            (1, "exit code=1"),
            (-11, "killed by SIGSEGV"),
            (-9, "killed by SIGKILL"),
            (-99, "killed by signal 99"),
        ],
    )
    def test_describes_exit_status(self, returncode: int, expected: str) -> None:
        assert describe_exit(returncode) == expected


class TestLevels:
    @pytest.mark.parametrize(
        ("ros_level", "expected"),
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARN", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("FATAL", logging.ERROR),
        ],
    )
    def test_ros_level_maps_to_python_level(
        self, caplog: pytest.LogCaptureFixture, ros_level: str, expected: int
    ) -> None:
        RecordOutputLogger().feed(f"[{ros_level}] [1.0] [rosbag2_recorder]: hello\n".encode())

        assert _records(caplog) == [(expected, f"ros2 bag record: [{ros_level}] [1.0] [rosbag2_recorder]: hello")]

    def test_line_without_ros_level_is_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        RecordOutputLogger().feed(b"terminate called after throwing an instance of 'std::runtime_error'\n")

        assert _records(caplog) == [
            (logging.WARNING, "ros2 bag record: terminate called after throwing an instance of 'std::runtime_error'")
        ]


class TestLineSplitting:
    def test_strips_ansi_escapes_and_carriage_returns(self, caplog: pytest.LogCaptureFixture) -> None:
        RecordOutputLogger().feed(b"\x1b[0m[ERROR] [1.0] [rosbag2_storage]: No space left on device\x1b[0m\r\n")

        assert _records(caplog) == [
            (logging.ERROR, "ros2 bag record: [ERROR] [1.0] [rosbag2_storage]: No space left on device")
        ]

    def test_skips_blank_lines(self, caplog: pytest.LogCaptureFixture) -> None:
        RecordOutputLogger().feed(b"\r\n\n  \r\x1b[0m\n")

        assert caplog.records == []

    def test_joins_a_line_split_across_chunks(self, caplog: pytest.LogCaptureFixture) -> None:
        output = RecordOutputLogger()
        output.feed(b"[ERROR] [1.0] [x]: par")
        assert caplog.records == []

        output.feed(b"tial\n[WARN] [2.0] [x]: next\n")

        assert _records(caplog) == [
            (logging.ERROR, "ros2 bag record: [ERROR] [1.0] [x]: partial"),
            (logging.WARNING, "ros2 bag record: [WARN] [2.0] [x]: next"),
        ]

    def test_joins_a_multibyte_character_split_across_chunks(self, caplog: pytest.LogCaptureFixture) -> None:
        encoded = "[ERROR] [1.0] [x]: ディスク\n".encode()
        cut = encoded.index("ク".encode()) + 1
        output = RecordOutputLogger()
        output.feed(encoded[:cut])
        output.feed(encoded[cut:])

        assert _records(caplog) == [(logging.ERROR, "ros2 bag record: [ERROR] [1.0] [x]: ディスク")]


class TestFlush:
    def test_logs_the_trailing_partial_line(self, caplog: pytest.LogCaptureFixture) -> None:
        output = RecordOutputLogger()
        output.feed(b"what():  No space left on device")
        output.flush()

        assert _records(caplog) == [(logging.WARNING, "ros2 bag record: what():  No space left on device")]

    def test_logs_nothing_when_no_partial_line(self, caplog: pytest.LogCaptureFixture) -> None:
        output = RecordOutputLogger()
        output.feed(b"[ERROR] [1.0] [x]: done\n")
        output.flush()
        output.flush()

        assert len(caplog.records) == 1
