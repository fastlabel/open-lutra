"""Tests for field extraction and image decoding."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.features.lerobot_export.extract import decode_ros_image, extract_field_data

from ._fakes import FakeFloatArray, FakeJointState, FakeRawImage, make_image_message, make_png_bytes


def test_extract_default_joint_position() -> None:
    msg = FakeJointState(position=[0.0, 1.0, 2.0, 3.0])
    assert extract_field_data(msg, field=None).tolist() == [0.0, 1.0, 2.0, 3.0]


def test_extract_default_nested_joint_state() -> None:
    msg = SimpleNamespace(joint_state=SimpleNamespace(position=[7.0, 8.0]))
    assert extract_field_data(msg, field=None).tolist() == [7.0, 8.0]


def test_extract_default_falls_back_to_data() -> None:
    assert extract_field_data(FakeFloatArray(data=[1.5, 2.5]), field=None).tolist() == [1.5, 2.5]


def test_extract_default_no_vector() -> None:
    with pytest.raises(ValueError, match="Cannot extract a vector"):
        extract_field_data(SimpleNamespace(header="x"), field=None)


def test_extract_explicit_field_with_indices() -> None:
    msg = FakeJointState(position=[0.0], velocity=[5.0, 6.0, 7.0])
    assert extract_field_data(msg, field="velocity", indices=[2, 0]).tolist() == [7.0, 5.0]


def test_extract_indices_out_of_range_padded() -> None:
    msg = FakeFloatArray(data=[1.0, 2.0])
    assert extract_field_data(msg, field="data", indices=[0, 5]).tolist() == [1.0, 0.0]


def test_extract_explicit_field_missing() -> None:
    with pytest.raises(ValueError, match="has no field"):
        extract_field_data(FakeJointState(position=[0.0]), field="effort")


def test_extract_explicit_scalar_field() -> None:
    # std_msgs/Float64 .data is a scalar (e.g. gripper openness) → length-1 vector.
    msg = SimpleNamespace(data=0.55)
    assert extract_field_data(msg, field="data").tolist() == [0.55]


def test_extract_default_scalar_data() -> None:
    # Structure detection falls back to a scalar `data` field.
    assert extract_field_data(SimpleNamespace(data=0.55), field=None).tolist() == [0.55]


def test_decode_compressed_image() -> None:
    msg = make_image_message(height=3, width=4, value=200)
    out = decode_ros_image(msg)
    assert out.shape == (3, 4, 3)
    assert out.dtype == np.uint8
    assert int(out[0, 0, 0]) == 200


@pytest.mark.parametrize("encoding", ["rgb8", "bgr8"])
def test_decode_raw_rgb(encoding: str) -> None:
    raw = np.arange(2 * 2 * 3, dtype=np.uint8).reshape(2, 2, 3)
    msg = FakeRawImage(encoding, 2, 2, raw.tobytes())
    out = decode_ros_image(msg)
    assert out.shape == (2, 2, 3)
    if encoding == "rgb8":
        assert np.array_equal(out, raw)
    else:
        assert np.array_equal(out, raw[:, :, ::-1])


@pytest.mark.parametrize("encoding", ["rgba8", "bgra8"])
def test_decode_raw_rgba(encoding: str) -> None:
    raw = np.arange(2 * 2 * 4, dtype=np.uint8).reshape(2, 2, 4)
    out = decode_ros_image(FakeRawImage(encoding, 2, 2, raw.tobytes()))
    assert out.shape == (2, 2, 3)


@pytest.mark.parametrize("encoding", ["mono8", "8UC1"])
def test_decode_raw_mono8(encoding: str) -> None:
    raw = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    out = decode_ros_image(FakeRawImage(encoding, 2, 2, raw.tobytes()))
    assert out.shape == (2, 2, 3)
    assert np.array_equal(out[:, :, 0], out[:, :, 2])


@pytest.mark.parametrize("encoding", ["mono16", "16UC1"])
def test_decode_raw_mono16(encoding: str) -> None:
    raw = np.array([[256, 512], [768, 1024]], dtype=np.uint16)
    out = decode_ros_image(FakeRawImage(encoding, 2, 2, raw.tobytes()))
    assert out.shape == (2, 2, 3)
    assert int(out[0, 0, 0]) == 1  # 256 / 256


def test_decode_unsupported_encoding() -> None:
    with pytest.raises(ValueError, match="Unsupported image encoding"):
        decode_ros_image(FakeRawImage("yuv422", 1, 1, b"\x00\x00"))


def test_decode_non_image() -> None:
    with pytest.raises(ValueError, match="not an image"):
        decode_ros_image(FakeJointState(position=[0.0]))


def test_make_png_roundtrip() -> None:
    rgb = np.full((2, 2, 3), 77, dtype=np.uint8)
    out = decode_ros_image(type("Msg", (), {"format": "png", "data": make_png_bytes(rgb)})())
    assert int(out[0, 0, 0]) == 77
