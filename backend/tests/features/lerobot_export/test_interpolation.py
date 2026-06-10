"""Tests for interpolation strategies."""

import numpy as np
import pytest

from app.features.lerobot_export.interpolation import (
    LinearInterpolator,
    NearestInterpolator,
    TimestampedValue,
    get_interpolator,
)


def _values(*pairs: tuple[int, list[float]]) -> list[TimestampedValue]:
    return [TimestampedValue(timestamp_ns=ts, value=np.array(v, dtype=np.float64)) for ts, v in pairs]


def test_get_interpolator() -> None:
    assert get_interpolator("linear").name == "linear"
    assert get_interpolator("nearest").name == "nearest"


def test_get_interpolator_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown interpolation"):
        get_interpolator("spline")


def test_linear_empty_returns_none() -> None:
    assert LinearInterpolator().interpolate([0, 1], [], 10) == [None, None]


def test_linear_single_point_holds_value() -> None:
    out = LinearInterpolator().interpolate([0, 5, 10], _values((3, [1.0, 2.0])), 100)
    assert all(np.array_equal(v, np.array([1.0, 2.0])) for v in out)


def test_linear_interpolates_and_holds_boundaries() -> None:
    source = _values((0, [0.0]), (10, [10.0]))
    out = LinearInterpolator().interpolate([-5, 0, 5, 10, 20], source, 1_000)
    assert [float(v[0]) for v in out] == [0.0, 0.0, 5.0, 10.0, 10.0]


def test_linear_same_timestamp_holds_left() -> None:
    source = _values((5, [1.0]), (5, [9.0]))
    out = LinearInterpolator().interpolate([5], source, 1_000)
    assert float(out[0][0]) == 1.0


def test_nearest_empty_returns_none() -> None:
    assert NearestInterpolator().interpolate([0], [], 10) == [None]


def test_nearest_within_and_outside_tolerance() -> None:
    source = _values((0, [1.0]), (100, [2.0]))
    out = NearestInterpolator().interpolate([5, 60], source, tolerance_ns=10)
    assert float(out[0][0]) == 1.0  # within tolerance of t=0
    assert out[1] is None  # 60 is >10ns from both 0 and 100
