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


def test_image_stats_empty_count_guard() -> None:
    # No frames folded: count is 0 and the pixel guard keeps moments at 0.
    out = ImageStats(channels=3).stats()
    assert out["count"] == [0]
    assert out["mean"] == [[[0.0]], [[0.0]], [[0.0]]]


def test_image_stats_min_max_per_channel() -> None:
    # Distinct per-channel ranges to confirm min/max recover the first/last
    # populated histogram bins independently per channel.
    accum = ImageStats(channels=3)
    accum.add(np.array([[[10, 20, 30]]], dtype=np.uint8))
    accum.add(np.array([[[40, 200, 90]]], dtype=np.uint8))
    out = accum.stats()
    assert out["min"] == [[[10 / 255]], [[20 / 255]], [[30 / 255]]]
    assert out["max"] == [[[40 / 255]], [[200 / 255]], [[90 / 255]]]


def test_image_stats_histogram_matches_direct_reduction() -> None:
    # The histogram path must match a direct float64 reduction bit-for-bit.
    rng = np.random.default_rng(0)
    frames = [rng.integers(0, 256, size=(4, 5, 3), dtype=np.uint8) for _ in range(7)]

    accum = ImageStats(channels=3)
    flats = []
    for frame in frames:
        accum.add(frame)
        flats.append(frame.reshape(-1, 3).astype(np.float64) / 255.0)
    stacked = np.concatenate(flats, axis=0)
    out = accum.stats()
    assert np.allclose([x[0][0] for x in out["mean"]], stacked.mean(axis=0))
    assert np.allclose([x[0][0] for x in out["std"]], stacked.std(axis=0))
    assert np.allclose([x[0][0] for x in out["min"]], stacked.min(axis=0))
    assert np.allclose([x[0][0] for x in out["max"]], stacked.max(axis=0))


def test_image_stats_fold_shares_one_histogram() -> None:
    # fold() lets one precomputed histogram feed multiple accumulators
    # (writer folds into global + per-episode without re-reducing).
    image = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
    histogram = ImageStats.histogram(image, 3)
    a, b = ImageStats(3), ImageStats(3)
    a.fold(histogram)
    b.fold(histogram)
    a_direct = ImageStats(3)
    a_direct.add(image)
    assert a.stats() == b.stats() == a_direct.stats()
