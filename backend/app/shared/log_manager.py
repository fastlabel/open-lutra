"""Application-wide log management module.

Centralizes logs from every subsystem (topic monitor, recording, file
operations, etc.). Thread-safe, and delivered incrementally over SSE.
"""

import threading
import time
from collections import deque
from typing import Literal

from pydantic import BaseModel, Field

LogSeverity = Literal["info", "warning", "danger"]


class LogEntry(BaseModel):
    """Log entry (domain model and API schema).

    The same shape is used both for internal storage in LogManager and for SSE
    delivery. The ``source`` field is used on the frontend to distinguish UI vs.
    API logs; it is always None for entries emitted by the backend.
    """

    id: int
    timestamp: float
    severity: str = Field(..., pattern=r"^(info|warning|danger)$")
    message: str
    topic: str | None = None
    source: str | None = None


class LogManager:
    """Thread-safe singleton that manages application-wide logs.

    Called from multiple subsystems such as TopicMonitor and the recording API.
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._lock = threading.Lock()
        self._logs: deque[LogEntry] = deque(maxlen=max_entries)
        self._counter = 0

    def add(self, severity: LogSeverity, message: str, topic: str | None = None) -> None:
        """Append a log entry (thread-safe)."""
        with self._lock:
            self._counter += 1
            entry = LogEntry(
                id=self._counter,
                timestamp=time.time(),
                severity=severity,
                message=message,
                topic=topic,
            )
            self._logs.append(entry)

    def get_logs(
        self,
        severity: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[LogEntry], int]:
        """Return log entries (supports severity filtering and pagination).

        Currently used for inspecting internal state from tests. When exposing
        this over an HTTP API, repack the result into ``LogsResponse`` in the
        router.
        """
        with self._lock:
            entries = list(self._logs)

        if severity:
            allowed = {s.strip() for s in severity.split(",")}
            entries = [e for e in entries if e.severity in allowed]

        total = len(entries)
        sliced = entries[offset : offset + limit]
        return (sliced, total)

    def get_logs_since(self, last_id: int) -> list[LogEntry]:
        """Return log entries newer than the given ID.

        Used by: GET /api/topics/stream (SSE).
        """
        with self._lock:
            return [e for e in self._logs if e.id > last_id]


# Global instance (initialized in main.py at application startup)
_log_manager: LogManager | None = None


def get_log_manager() -> LogManager:  # pragma: no cover
    if _log_manager is None:
        raise RuntimeError("LogManager is not initialized")
    return _log_manager


def set_log_manager(manager: LogManager) -> None:  # pragma: no cover
    """Set the global LogManager instance (called at application startup)."""
    global _log_manager
    _log_manager = manager
