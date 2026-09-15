"""Unit tests for LogManager."""

from app.shared.log_manager import LogManager


class TestLogManagerAdd:
    """Tests for LogManager.add()."""

    def test_add_increments_counter(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "message1")
        lm.add("warning", "message2")
        logs, total = lm.get_logs()
        assert total == 2
        assert logs[0].id == 1
        assert logs[1].id == 2

    def test_add_with_topic(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "test", "/joint_states")
        logs, _ = lm.get_logs()
        assert logs[0].topic == "/joint_states"

    def test_max_entries_enforced(self) -> None:
        lm = LogManager(max_entries=3)
        for i in range(5):
            lm.add("info", f"message{i}")
        logs, total = lm.get_logs()
        assert total == 3
        assert logs[0].message == "message2"  # Older entries are dropped


class TestLogManagerGetLogs:
    """Tests for LogManager.get_logs()."""

    def test_severity_filter(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "info")
        lm.add("warning", "warning")
        lm.add("danger", "danger")
        lm.add("info", "info2")

        logs, total = lm.get_logs(severity="warning")
        assert total == 1
        assert logs[0].severity == "warning"

    def test_multiple_severity_filter(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "info")
        lm.add("warning", "warning")
        lm.add("danger", "danger")

        _logs, total = lm.get_logs(severity="warning,danger")
        assert total == 2

    def test_pagination(self) -> None:
        lm = LogManager(max_entries=100)
        for i in range(10):
            lm.add("info", f"message{i}")

        logs, total = lm.get_logs(limit=3, offset=2)
        assert total == 10
        assert len(logs) == 3
        assert logs[0].message == "message2"

    def test_empty(self) -> None:
        lm = LogManager(max_entries=100)
        logs, total = lm.get_logs()
        assert total == 0
        assert logs == []


class TestLogManagerGetLogsSince:
    """Tests for LogManager.get_logs_since()."""

    def test_returns_new_entries(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "old log")
        lm.add("info", "new log")

        entries = lm.get_logs_since(1)
        assert len(entries) == 1
        assert entries[0].message == "new log"

    def test_returns_empty_when_no_new(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "log")
        entries = lm.get_logs_since(1)
        assert entries == []

    def test_returns_all_when_id_zero(self) -> None:
        lm = LogManager(max_entries=100)
        lm.add("info", "log1")
        lm.add("info", "log2")
        entries = lm.get_logs_since(0)
        assert len(entries) == 2
