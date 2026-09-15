"""Fault simulation logic.

Centralizes the decision logic for each mode. Independent of ROS2.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

from config import (
    BURST_COUNT,
    BURST_GAP_SEC,
    BURST_INTERVAL_SEC,
    DROP_RATE,
    EMPTY_CAMERA_INDICES,
    EMPTY_FRAME_RATE,
    MIXED_RECOVERY_SEC,
    MIXED_RESTOP_SEC,
    STOP_AFTER_SEC,
    STOP_TOPICS,
    UNSTABLE_TOPICS,
    UNSTABLE_TOPICS_ALL,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class FaultInjector:
    """Manages fault injection for the simulator.

    Each predicate method is enabled or disabled based on the active mode.
    """

    def __init__(self, mode: str, log: Callable[[str, str], None]) -> None:
        self._mode = mode
        self._log = log  # (level, message) -> None
        self._start_time = time.monotonic()

        # topic_stop: flag set of already-stopped topics (prevents duplicate logs)
        self._stop_logged: set[str] = set()

        # burst: state tracking
        self._burst_state = "normal"  # "normal" | "gap" | "burst"
        self._burst_gap_start = 0.0
        self._burst_remaining = 0
        self._last_burst_cycle = 0.0

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    # --- unstable ---

    def should_drop(self, topic_name: str) -> bool:
        """unstable mode: whether to drop the message."""
        if self._mode not in ("unstable", "mixed"):
            return False
        if not UNSTABLE_TOPICS_ALL and topic_name not in UNSTABLE_TOPICS:
            return False
        return random.random() < DROP_RATE

    # --- topic_stop ---

    def is_stopped(self, topic_name: str) -> bool:
        """topic_stop mode: whether the topic is currently stopped.

        In mixed mode this repeats a stop → recovery → re-stop cycle.
        """
        if self._mode not in ("topic_stop", "mixed"):
            return False
        if topic_name not in STOP_TOPICS:
            return False

        elapsed = self._elapsed()
        if elapsed < STOP_AFTER_SEC:
            return False

        # topic_stop: permanent stop
        if self._mode == "topic_stop":
            if topic_name not in self._stop_logged:
                self._stop_logged.add(topic_name)
                self._log("warn", f"[topic_stop] stopped publishing {topic_name}")
            return True

        cycle_start = elapsed - STOP_AFTER_SEC
        cycle_len = MIXED_RECOVERY_SEC + MIXED_RESTOP_SEC
        phase = cycle_start % cycle_len
        stopped = phase >= MIXED_RECOVERY_SEC  # recovery first, then stopped

        key = f"{topic_name}:{stopped}"
        if key not in self._stop_logged:
            self._stop_logged.add(key)
            if stopped:
                self._log("warn", f"[mixed] stopped publishing {topic_name}")
            else:
                # Clear the previous stop log so re-stop can log again
                self._stop_logged.discard(f"{topic_name}:True")
                self._log("info", f"[mixed] publishing of {topic_name} recovered")

        return stopped

    # --- camera_empty ---

    def should_send_empty_frame(self, camera_idx: int) -> bool:
        """camera_empty mode: whether to send an empty frame."""
        if self._mode not in ("camera_empty", "mixed"):
            return False
        if camera_idx not in EMPTY_CAMERA_INDICES:
            return False
        return random.random() < EMPTY_FRAME_RATE

    # --- burst ---

    def update_burst(self) -> str:
        """burst mode: update state and return "normal" / "gap" / "burst"."""
        if self._mode != "burst":
            return "normal"

        elapsed = self._elapsed()

        if self._burst_state == "normal":
            if elapsed - self._last_burst_cycle >= BURST_INTERVAL_SEC:
                self._burst_state = "gap"
                self._burst_gap_start = elapsed
                self._log("info", f"[burst] gap start (publishing stopped for {BURST_GAP_SEC}s)")
            return "normal"

        if self._burst_state == "gap":
            if elapsed - self._burst_gap_start >= BURST_GAP_SEC:
                self._burst_state = "burst"
                self._burst_remaining = BURST_COUNT
                self._log("info", f"[burst] burst start (sending {BURST_COUNT} messages at once)")
            return "gap"

        # burst
        if self._burst_remaining <= 0:
            self._burst_state = "normal"
            self._last_burst_cycle = elapsed
            self._log("info", "[burst] burst complete, back to normal publishing")
            return "normal"
        return "burst"

    def consume_burst(self, count: int) -> None:
        self._burst_remaining -= count

    @property
    def burst_remaining(self) -> int:
        return self._burst_remaining

    def log_config(self) -> None:
        mode = self._mode
        if mode == "normal":
            self._log("info", "Mode: normal (stable publishing)")
        elif mode == "unstable":
            self._log("info", f"Mode: unstable (drop_rate={DROP_RATE}, targets={UNSTABLE_TOPICS})")
        elif mode == "topic_stop":
            self._log("info", f"Mode: topic_stop (stop {STOP_TOPICS} after {STOP_AFTER_SEC}s)")
        elif mode == "camera_empty":
            self._log("info", f"Mode: camera_empty (cameras={EMPTY_CAMERA_INDICES}, rate={EMPTY_FRAME_RATE})")
        elif mode == "burst":
            self._log(
                "info", f"Mode: burst (interval={BURST_INTERVAL_SEC}s, gap={BURST_GAP_SEC}s, count={BURST_COUNT})"
            )
        elif mode == "mixed":
            self._log(
                "info",
                f"Mode: mixed (unstable + stop/recovery cycle [{MIXED_RECOVERY_SEC}s recovery → {MIXED_RESTOP_SEC}s stop] + camera_empty)",
            )
