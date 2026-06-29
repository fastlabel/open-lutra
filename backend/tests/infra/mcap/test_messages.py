"""Tests for structure-based MCAP message detection / extraction."""

from types import SimpleNamespace

from app.infra.mcap.messages import extract_joint_names, extract_joint_positions, is_image_message


class TestIsImageMessage:
    def test_compressed_image_like(self) -> None:
        assert is_image_message(SimpleNamespace(format="jpeg", data=b"\xff\xd8")) is True

    def test_bytearray_data(self) -> None:
        assert is_image_message(SimpleNamespace(format="raw", data=bytearray(b"x"))) is True

    def test_data_not_bytes(self) -> None:
        assert is_image_message(SimpleNamespace(format="jpeg", data=[1, 2, 3])) is False

    def test_missing_format(self) -> None:
        assert is_image_message(SimpleNamespace(data=b"x")) is False


class TestExtractJointPositions:
    def test_standard_joint_state(self) -> None:
        assert extract_joint_positions(SimpleNamespace(position=[1.0, 2.0])) == [1.0, 2.0]

    def test_wrapped_joint_state(self) -> None:
        msg = SimpleNamespace(joint_state=SimpleNamespace(position=[3.0]))
        assert extract_joint_positions(msg) == [3.0]

    def test_composite_with_neck(self) -> None:
        msg = SimpleNamespace(
            joint_state=SimpleNamespace(position=[1.0]),
            neck_joint_state=SimpleNamespace(position=[9.0]),
        )
        assert extract_joint_positions(msg) == [1.0, 9.0]

    def test_no_position_returns_empty(self) -> None:
        assert extract_joint_positions(SimpleNamespace(foo=1)) == []


class TestExtractJointNames:
    def test_standard_joint_state(self) -> None:
        assert extract_joint_names(SimpleNamespace(name=["a", "b"])) == ["a", "b"]

    def test_wrapped_joint_state(self) -> None:
        msg = SimpleNamespace(joint_state=SimpleNamespace(name=["j1"]))
        assert extract_joint_names(msg) == ["j1"]

    def test_composite_with_neck(self) -> None:
        msg = SimpleNamespace(
            joint_state=SimpleNamespace(name=["a"]),
            neck_joint_state=SimpleNamespace(name=["neck"]),
        )
        assert extract_joint_names(msg) == ["a", "neck"]

    def test_no_name_returns_empty(self) -> None:
        assert extract_joint_names(SimpleNamespace(position=[1.0])) == []
