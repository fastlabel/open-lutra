"""Interpolation strategies for resampling state/action sources onto the fps timebase.

Each strategy maps a series of timestamped vectors to a value per reference
timestamp. Values outside the source range are held at the boundary (no
extrapolation); `nearest` returns None when no source point lies within tolerance.
"""

from __future__ import annotations

import bisect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class TimestampedValue:
    """A vector value with its source timestamp (nanoseconds)."""

    timestamp_ns: int
    value: NDArray[np.float64]


class Interpolator(ABC):
    """Maps timestamped source vectors to values at reference timestamps."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical name of this strategy."""

    @abstractmethod
    def interpolate(
        self,
        ref_timestamps: list[int],
        source_data: list[TimestampedValue],
        tolerance_ns: int,
    ) -> list[NDArray[np.float64] | None]:
        """Return one interpolated vector (or None) per reference timestamp."""


class LinearInterpolator(Interpolator):
    """Linear interpolation between the two nearest source points.

    Holds the boundary value outside the source range. Suitable for continuous
    signals such as joint positions and velocities.
    """

    @property
    def name(self) -> str:
        return "linear"

    def interpolate(
        self,
        ref_timestamps: list[int],
        source_data: list[TimestampedValue],
        _tolerance_ns: int,
    ) -> list[NDArray[np.float64] | None]:
        # Linear interpolation always blends between bracketing samples and holds
        # the boundary value outside the source range, so tolerance is unused.
        if not source_data:
            return [None] * len(ref_timestamps)
        if len(source_data) == 1:
            single = source_data[0].value
            return [single.copy() for _ in ref_timestamps]

        source_ts = [d.timestamp_ns for d in source_data]
        return [self._interpolate_single(ts, source_ts, source_data) for ts in ref_timestamps]

    def _interpolate_single(
        self,
        ts: int,
        source_ts: list[int],
        source_data: list[TimestampedValue],
    ) -> NDArray[np.float64]:
        idx = bisect.bisect_left(source_ts, ts)
        if idx == 0:
            first: NDArray[np.float64] = source_data[0].value.copy()
            return first
        if idx >= len(source_ts):
            last: NDArray[np.float64] = source_data[-1].value.copy()
            return last

        # idx is strictly inside the source range here, and bisect_left resolves
        # any duplicate-timestamp run to its left edge, so t1 > t0 always holds.
        t0, t1 = source_ts[idx - 1], source_ts[idx]
        v0, v1 = source_data[idx - 1].value, source_data[idx].value
        alpha = (ts - t0) / (t1 - t0)
        interpolated: NDArray[np.float64] = (v0 + (v1 - v0) * alpha).astype(np.float64)
        return interpolated


class NearestInterpolator(Interpolator):
    """Nearest-neighbor selection within tolerance.

    Returns None when no source point lies within `tolerance_ns`. Suitable for
    discrete states that should not be blended.
    """

    @property
    def name(self) -> str:
        return "nearest"

    def interpolate(
        self,
        ref_timestamps: list[int],
        source_data: list[TimestampedValue],
        tolerance_ns: int,
    ) -> list[NDArray[np.float64] | None]:
        if not source_data:
            return [None] * len(ref_timestamps)

        source_ts = [d.timestamp_ns for d in source_data]
        results: list[NDArray[np.float64] | None] = []
        for ts in ref_timestamps:
            idx = bisect.bisect_left(source_ts, ts)
            best: TimestampedValue | None = None
            best_diff = tolerance_ns + 1
            for candidate in (idx - 1, idx):
                if 0 <= candidate < len(source_ts):
                    diff = abs(source_ts[candidate] - ts)
                    if diff < best_diff:
                        best_diff = diff
                        best = source_data[candidate]
            results.append(best.value.copy() if best is not None else None)
        return results


_INTERPOLATORS: dict[str, Interpolator] = {
    "linear": LinearInterpolator(),
    "nearest": NearestInterpolator(),
}


def get_interpolator(name: str) -> Interpolator:
    """Return the interpolator for `name`.

    Raises:
        ValueError: If the name is not a known strategy.
    """
    interpolator = _INTERPOLATORS.get(name)
    if interpolator is None:
        raise ValueError(f"Unknown interpolation strategy: {name!r} (expected 'linear' or 'nearest')")
    return interpolator
