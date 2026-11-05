"""Run an encode down a ladder of steps until one succeeds."""

from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import TypeVar

StepT = TypeVar("StepT")
ResultT = TypeVar("ResultT")


class VideoEncodeError(RuntimeError):
    """An ffmpeg encode failed (non-zero exit, or ffmpeg stopped reading its input)."""


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
