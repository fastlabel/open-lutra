"""Tests for field extraction and image decoding."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.features.lerobot_export.extract import decode_ros_image, extract_field_data

from ._fakes import FakeFloatArray, FakeJointState, FakeRawImage, make_image_message, make_png_bytes

# --- extract_field_data: type=number ---

def test_extract_number_scalar_float() -> None:
    msg = SimpleNamespace(gripper_pos=0.75)
    assert extract_field_data(msg, "gripper_pos", "number").tolist() == [0.75]


def test_extract_number_via_dot_path() -> None:
    msg = SimpleNamespace(arm=SimpleNamespace(speed=1.5))
    assert extract_field_data(msg, "arm.speed", "number").tolist() == [1.5]


# --- extract_field_data: type=list ---

def test_extract_list_with_indices() -> None:
    msg = FakeJointState(position=[0.0, 1.0, 2.0, 3.0])
    assert extract_field_data(msg, "position", "list", indices=[3, 1]).tolist() == [3.0, 1.0]


def test_extract_list_dot_path() -> None:
    msg = SimpleNamespace(joint_state=FakeJointState(position=[10.0, 20.0, 30.0]))
    assert extract_field_data(msg, "joint_state.position", "list", indices=[0, 2]).tolist() == [10.0, 30.0]


def test_extract_list_indices_out_of_range_padded() -> None:
    msg = FakeFloatArray(data=[1.0, 2.0])
    assert extract_field_data(msg, "data", "list", indices=[0, 5]).tolist() == [1.0, 0.0]


def test_extract_list_missing_indices_raises() -> None:
    msg = FakeJointState(position=[0.0, 1.0])
    with pytest.raises(ValueError, match="indices"):
        extract_field_data(msg, "position", "list")


# --- extract_field_data: type=struct ---

def test_extract_struct_with_keys() -> None:
    msg = SimpleNamespace(pose=SimpleNamespace(position=SimpleNamespace(x=1.0, y=2.0, z=3.0)))
    result = extract_field_data(msg, "pose.position", "struct", keys=["x", "y", "z"])
    assert result.tolist() == [1.0, 2.0, 3.0]


def test_extract_struct_no_field_applies_keys_to_decoded() -> None:
    # geometry_msgs/Point published as top-level: field=None, keys on decoded directly
    msg = SimpleNamespace(x=-0.183, y=0.481, z=0.274)
    result = extract_field_data(msg, None, "struct", keys=["x", "y", "z"])
    assert result.tolist() == pytest.approx([-0.183, 0.481, 0.274])


def test_extract_struct_partial_keys() -> None:
    msg = SimpleNamespace(pos=SimpleNamespace(x=5.0, y=6.0, z=7.0))
    assert extract_field_data(msg, "pos", "struct", keys=["x", "z"]).tolist() == [5.0, 7.0]


def test_extract_struct_missing_keys_raises() -> None:
    msg = SimpleNamespace(pos=SimpleNamespace(x=1.0))
    with pytest.raises(ValueError, match="keys"):
        extract_field_data(msg, "pos", "struct")


def test_extract_struct_key_not_found_raises() -> None:
    msg = SimpleNamespace(pos=SimpleNamespace(x=1.0))
    with pytest.raises(ValueError, match="pos"):
        extract_field_data(msg, "pos", "struct", keys=["x", "w"])


# --- error cases ---

def test_extract_missing_field_raises() -> None:
    with pytest.raises(ValueError, match="has no field"):
        extract_field_data(FakeJointState(position=[0.0]), "effort", "list", indices=[0])


def test_extract_missing_dot_path_raises() -> None:
    with pytest.raises(ValueError, match="has no field"):
        extract_field_data(SimpleNamespace(a=SimpleNamespace()), "a.b.c", "number")


def test_extract_unknown_type_raises() -> None:
    msg = FakeJointState(position=[0.0])
    with pytest.raises(ValueError, match="Unknown field type"):
        extract_field_data(msg, "position", "vector", indices=[0])


# --- decode_ros_image ---

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
