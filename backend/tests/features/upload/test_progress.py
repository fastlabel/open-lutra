"""Tests for the throttled boto3 progress callback."""

from app.features.upload.progress import ThrottledProgress


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class TestThrottledProgress:
    def test_emits_first_update_immediately(self) -> None:
        seen: list[int] = []
        clock = _Clock()
        clock.t = 100.0  # any non-zero start

        progress = ThrottledProgress(seen.append, interval_sec=1.0, now=clock)
        progress(50)
        assert seen == [50]

    def test_throttles_subsequent_updates(self) -> None:
        seen: list[int] = []
        clock = _Clock()
        clock.t = 100.0

        progress = ThrottledProgress(seen.append, interval_sec=1.0, now=clock)
        progress(50)  # emits → seen=[50]

        clock.t = 100.5  # half the interval
        progress(50)  # suppressed (still 0.5s since last emit)

        clock.t = 101.5  # full interval elapsed
        progress(50)  # emits the running total

        assert seen == [50, 150]

    def test_close_emits_final_value(self) -> None:
        seen: list[int] = []
        clock = _Clock()
        clock.t = 100.0

        progress = ThrottledProgress(seen.append, interval_sec=1.0, now=clock)
        progress(50)
        clock.t = 100.1
        progress(50)  # suppressed
        total = progress.close()

        assert total == 100
        assert seen == [50, 100]  # the final close() always fires
