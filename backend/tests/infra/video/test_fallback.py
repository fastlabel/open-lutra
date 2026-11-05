"""Tests for the fallback ladder runner."""

import pytest

from app.infra.video import VideoEncodeError, run_with_fallback


class _Recorder:
    """Attempt function whose outcome per step is scripted."""

    def __init__(self, outcomes: dict[str, Exception | str]) -> None:
        self.outcomes = outcomes
        self.attempted: list[str] = []
        self.fallbacks: list[tuple[str, str, str]] = []

    def attempt(self, step: str) -> str:
        self.attempted.append(step)
        outcome = self.outcomes[step]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def on_fallback(self, failed: str, nxt: str, error: Exception) -> None:
        self.fallbacks.append((failed, nxt, str(error)))


def _is_encode_error(error: Exception) -> bool:
    return isinstance(error, VideoEncodeError)


def _run(recorder: _Recorder, steps: list[str]) -> str:
    return run_with_fallback(steps, recorder.attempt, should_retry=_is_encode_error, on_fallback=recorder.on_fallback)


def test_first_step_succeeds() -> None:
    recorder = _Recorder({"gpu": "ok-gpu", "cpu": "ok-cpu"})
    assert _run(recorder, ["gpu", "cpu"]) == "ok-gpu"
    assert recorder.attempted == ["gpu"]
    assert recorder.fallbacks == []


def test_falls_back_until_a_step_succeeds() -> None:
    recorder = _Recorder({"a": VideoEncodeError("a failed"), "b": VideoEncodeError("b failed"), "c": "ok-c"})
    assert _run(recorder, ["a", "b", "c"]) == "ok-c"
    assert recorder.attempted == ["a", "b", "c"]
    assert recorder.fallbacks == [("a", "b", "a failed"), ("b", "c", "b failed")]


def test_last_step_failure_is_reraised() -> None:
    recorder = _Recorder({"gpu": VideoEncodeError("gpu failed"), "cpu": VideoEncodeError("cpu failed")})
    with pytest.raises(VideoEncodeError, match="cpu failed"):
        _run(recorder, ["gpu", "cpu"])
    assert recorder.fallbacks == [("gpu", "cpu", "gpu failed")]


def test_non_encoder_error_is_not_retried() -> None:
    recorder = _Recorder({"gpu": OSError("MCAP truncated"), "cpu": "ok-cpu"})
    with pytest.raises(OSError, match="MCAP truncated"):
        _run(recorder, ["gpu", "cpu"])
    assert recorder.attempted == ["gpu"]
    assert recorder.fallbacks == []


def test_single_step_runs_once() -> None:
    recorder = _Recorder({"cpu": "ok-cpu"})
    assert _run(recorder, ["cpu"]) == "ok-cpu"


def test_empty_ladder_is_rejected() -> None:
    with pytest.raises(ValueError, match="At least one step"):
        _run(_Recorder({}), [])
