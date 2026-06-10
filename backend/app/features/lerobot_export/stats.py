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
        self._sum = np.zeros(self.dim, dtype=np.float64)
        self._sumsq = np.zeros(self.dim, dtype=np.float64)
        self._min = np.full(self.dim, np.inf, dtype=np.float64)
        self._max = np.full(self.dim, -np.inf, dtype=np.float64)

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
    """Per-channel running statistics over normalized image pixels ([0, 1])."""

    channels: int = 3

    def __post_init__(self) -> None:
        self._frames = 0
        self._pixels = 0
        self._sum = np.zeros(self.channels, dtype=np.float64)
        self._sumsq = np.zeros(self.channels, dtype=np.float64)
        self._min = np.full(self.channels, np.inf, dtype=np.float64)
        self._max = np.full(self.channels, -np.inf, dtype=np.float64)

    def add(self, value: NDArray[Any]) -> None:
        norm = value.astype(np.float64) / 255.0
        flat = norm.reshape(-1, self.channels)
        self._frames += 1
        self._pixels += flat.shape[0]
        self._sum += flat.sum(axis=0)
        self._sumsq += (flat * flat).sum(axis=0)
        self._min = np.minimum(self._min, flat.min(axis=0))
        self._max = np.maximum(self._max, flat.max(axis=0))

    def stats(self) -> StatsDict:
        pixels = max(self._pixels, 1)
        mean = self._sum / pixels
        variance = np.maximum(self._sumsq / pixels - mean * mean, 0.0)
        std = np.sqrt(variance)
        return {
            "min": _as_channel_shape(self._min),
            "max": _as_channel_shape(self._max),
            "mean": _as_channel_shape(mean),
            "std": _as_channel_shape(std),
            "count": [self._frames],
        }


def _as_channel_shape(per_channel: NDArray[np.float64]) -> list[list[list[float]]]:
    """Reshape a per-channel vector into the LeRobot `(channels, 1, 1)` nesting."""
    return [[[float(value)]] for value in per_channel]
