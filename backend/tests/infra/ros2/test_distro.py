"""Tests for the ROS 2 distro differences."""

import pytest

from app.infra.ros2.distro import HUMBLE, JAZZY, RosDistro, current_distro


class TestTopicArgs:
    def test_humble_passes_topics_positionally(self) -> None:
        assert HUMBLE.topic_args(["/a", "/b"]) == ["/a", "/b"]

    def test_jazzy_uses_topics_flag(self) -> None:
        assert JAZZY.topic_args(["/a", "/b"]) == ["--topics", "/a", "/b"]


class TestCurrentDistro:
    @pytest.mark.parametrize("distro", [HUMBLE, JAZZY])
    def test_resolves_supported_distro(self, monkeypatch: pytest.MonkeyPatch, distro: RosDistro) -> None:
        monkeypatch.setenv("ROS_DISTRO", distro.name)
        assert current_distro() is distro

    @pytest.mark.parametrize("value", ["rolling", None])
    def test_rejects_unsupported_or_unset(self, monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("ROS_DISTRO", raising=False)
        else:
            monkeypatch.setenv("ROS_DISTRO", value)
        with pytest.raises(ValueError, match="Unsupported ROS_DISTRO"):
            current_distro()
