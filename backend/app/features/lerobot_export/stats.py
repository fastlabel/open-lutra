"""Incremental feature statistics for LeRobot `meta/stats.json` and per-episode stats.

Vector features (`action`, `observation.<field>`) accumulate per-dimension
min/max/mean/std over frames. Image features accumulate per-channel stats over
all pixels of all frames, normalized to [0, 1] and shaped `(channels, 1, 1)` —
matching the LeRobot v3.0 convention.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Each feature's stats are {min, max, mean, std, count}, every value a list
# (per-dimension for vectors, nested per-channel for images, length-1 for count).
StatsDict = dict[str, list[Any]]


class StatsAccumulator(ABC):
    """Folds frames into running min/max/mean/std/count statistics."""

    @abstractmethod
    def add(self, value: NDArray[Any]) -> None:
        """Fold one frame's value into the running statistics."""

    @abstractmethod
    def stats(self) -> StatsDict:
        """Return the {min, max, mean, std, count} stats dict for this feature."""


@dataclass
class VectorStats(StatsAccumulator):
    """Per-dimension running statistics for a fixed-length float vector."""

    dim: int

    def __post_init__(self) -> None:
        self._count = 0
        self._sum: NDArray[np.float64] = np.zeros(self.dim, dtype=np.float64)
        self._sumsq: NDArray[np.float64] = np.zeros(self.dim, dtype=np.float64)
        self._min: NDArray[np.float64] = np.full(self.dim, np.inf, dtype=np.float64)
        self._max: NDArray[np.float64] = np.full(self.dim, -np.inf, dtype=np.float64)

    def add(self, value: NDArray[Any]) -> None:
        vector = value.astype(np.float64)
        self._count += 1
        self._sum += vector
        self._sumsq += vector * vector
        self._min = np.minimum(self._min, vector)
        self._max = np.maximum(self._max, vector)

    def stats(self) -> StatsDict:
        count = max(self._count, 1)
        mean = self._sum / count
        variance = np.maximum(self._sumsq / count - mean * mean, 0.0)
        return {
            "min": self._min.tolist(),
            "max": self._max.tolist(),
            "mean": mean.tolist(),
            "std": np.sqrt(variance).tolist(),
            "count": [self._count],
        }


@dataclass
class ImageStats(StatsAccumulator):
    """Per-channel running statistics over normalized image pixels ([0, 1]).

    Accumulates a per-channel 256-bin pixel-value histogram rather than folding
    float64 reductions over every pixel of every frame. A histogram is a
    complete sufficient statistic for min/max/mean/std of uint8 pixels, so the
    result is identical to a direct reduction while the per-frame cost drops to a
    handful of `np.bincount` calls (the dominant cost in a large export). The
    value→[0, 1] normalization and the mean/std math are deferred to `stats()`,
    which runs once.
    """

    channels: int = 3

    def __post_init__(self) -> None:
        self._frames = 0
        # Per-channel histogram of raw pixel values (0..255).
        self._histogram: NDArray[np.int64] = np.zeros((self.channels, 256), dtype=np.int64)

    def add(self, value: NDArray[Any]) -> None:
        self.fold(self.histogram(value, self.channels))

    @staticmethod
    def histogram(value: NDArray[Any], channels: int = 3) -> NDArray[np.int64]:
        """Compute a per-channel 256-bin pixel-value histogram for one frame.

        Exposed so a caller can compute the histogram once and fold it into
        multiple accumulators (e.g. global + per-episode) without re-reducing.
        """
        flat = value.reshape(-1, channels)
        return np.stack([np.bincount(flat[:, c], minlength=256) for c in range(channels)])

    def fold(self, histogram: NDArray[np.int64]) -> None:
        """Fold one frame's precomputed per-channel histogram into the running stats."""
        self._frames += 1
        self._histogram += histogram

    def stats(self) -> StatsDict:
        values = np.arange(256, dtype=np.float64)
        counts = self._histogram.astype(np.float64)
        pixels = np.maximum(counts.sum(axis=1), 1.0)
        # Accumulate in raw pixel-value space, then normalize the moments to [0, 1].
        mean = (counts * values).sum(axis=1) / pixels / 255.0
        mean_sq = (counts * values * values).sum(axis=1) / pixels / (255.0**2)
        std = np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))
        present = counts > 0
        # First / last populated bin per channel = min / max pixel value.
        lo = np.array([np.argmax(row) if row.any() else 0 for row in present], dtype=np.float64)
        hi = np.array([255 - np.argmax(row[::-1]) if row.any() else 0 for row in present], dtype=np.float64)
        return {
            "min": _as_channel_shape(lo / 255.0),
            "max": _as_channel_shape(hi / 255.0),
            "mean": _as_channel_shape(mean),
            "std": _as_channel_shape(std),
            "count": [self._frames],
        }


def _as_channel_shape(per_channel: NDArray[np.float64]) -> list[list[list[float]]]:
    """Reshape a per-channel vector into the LeRobot `(channels, 1, 1)` nesting."""
    return [[[float(value)]] for value in per_channel]
