"""Run an encode down a ladder of steps until one succeeds."""

from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import TypeVar

from app.infra.video.commands import VideoEncodeError, VideoEncoder, encoder_ladder

StepT = TypeVar("StepT")
ResultT = TypeVar("ResultT")


def run_with_fallback(
    steps: Sequence[StepT],
    attempt: Callable[[StepT], ResultT],
    *,
    should_retry: Callable[[Exception], bool],
    on_fallback: Callable[[StepT, StepT, Exception], None],
) -> ResultT:
    """Return `attempt(step)` for the first step that succeeds.

    A failure moves on to the next step only when `should_retry(error)` holds
    and a next step exists; `on_fallback(failed_step, next_step, error)` is
    called before moving on. Any other failure, or a failure of the last step,
    is re-raised unchanged.
    """
    if not steps:
        raise ValueError("At least one step is required")
    for step, next_step in pairwise(steps):
        try:
            return attempt(step)
        except Exception as error:
            if not should_retry(error):
                raise
            on_fallback(step, next_step, error)
    return attempt(steps[-1])


def encode_with_fallback(
    encoder: VideoEncoder,
    attempt: Callable[[VideoEncoder], ResultT],
    *,
    on_fallback: Callable[[VideoEncoder, VideoEncoder, Exception], None],
) -> ResultT:
    """Run `attempt` down `encoder_ladder(encoder)`, moving on only after an ffmpeg failure.

    Only `VideoEncodeError` falls back: other errors (e.g. a corrupted MCAP)
    would fail the same way with any encoder, so they are raised as-is.
    """
    return run_with_fallback(encoder_ladder(encoder), attempt, should_retry=_is_encode_failure, on_fallback=on_fallback)


def _is_encode_failure(error: Exception) -> bool:
    return isinstance(error, VideoEncodeError)
