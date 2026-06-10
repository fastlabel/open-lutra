"""Tests for incremental feature statistics."""

import numpy as np

from app.features.lerobot_export.stats import ImageStats, VectorStats


def test_vector_stats() -> None:
    accum = VectorStats(dim=2)
    accum.add(np.array([0.0, 10.0]))
    accum.add(np.array([2.0, 20.0]))
    out = accum.stats()
    assert out["min"] == [0.0, 10.0]
    assert out["max"] == [2.0, 20.0]
    assert out["mean"] == [1.0, 15.0]
    assert out["count"] == [2]
    assert out["std"][0] == 1.0


def test_vector_stats_empty_count_guard() -> None:
    out = VectorStats(dim=1).stats()
    assert out["count"] == [0]
    assert out["mean"] == [0.0]


def test_image_stats_shape_and_values() -> None:
    accum = ImageStats(channels=3)
    accum.add(np.zeros((2, 2, 3), dtype=np.uint8))
    accum.add(np.full((2, 2, 3), 255, dtype=np.uint8))
    out = accum.stats()
    assert out["min"] == [[[0.0]], [[0.0]], [[0.0]]]
    assert out["max"] == [[[1.0]], [[1.0]], [[1.0]]]
    assert out["mean"] == [[[0.5]], [[0.5]], [[0.5]]]
    assert out["count"] == [2]
