"""Throttled progress callback for boto3 uploads.

boto3 invokes `Callback(bytes_transferred_delta)` after each part / chunk
finishes. For multi-GB MCAP recordings the callback fires hundreds of times
per second; persisting on every call would thrash disk and flood SSE
subscribers. `ThrottledProgress` accumulates the delta in memory and emits
at most once per `interval_sec` (default 1.0 s), plus a guaranteed final
flush on `close()`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock


class ThrottledProgress:
    """Accumulate byte progress; emit via `on_update` at most once per interval.

    Both the boto3 `Callback` invocation and `close()` are thread-safe: boto3
    calls the callback from worker threads when multipart uploads run with
    `max_concurrency > 1`.
    """

    def __init__(
        self,
        on_update: Callable[[int], None],
        *,
        interval_sec: float = 1.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._on_update = on_update
        self._interval_sec = interval_sec
        self._now = now
        self._lock = Lock()
        self._bytes = 0
        self._last_emit = 0.0

    def __call__(self, bytes_delta: int) -> None:
        """boto3 callback entry point."""
        with self._lock:
            self._bytes += bytes_delta
            current = self._now()
            if current - self._last_emit < self._interval_sec:
                return
            self._last_emit = current
            snapshot = self._bytes
        self._on_update(snapshot)

    def close(self) -> int:
        """Flush a final update (bypasses the throttle). Returns total bytes."""
        with self._lock:
            snapshot = self._bytes
            self._last_emit = self._now()
        self._on_update(snapshot)
        return snapshot
