"""Tests for ExportConfig domain helpers."""

from app.features.lerobot_export.models import ExportConfig, SourceConfig


def _src(topic: str) -> SourceConfig:
    return SourceConfig(topic=topic, field="position")


def test_all_topics_dedupes_and_preserves_order() -> None:
    config = ExportConfig(
        images={"cam_a": "/img_a", "cam_b": "/img_b"},
        observation={"state": [_src("/state"), _src("/img_a")]},  # /img_a repeated on purpose
        action=[_src("/cmd"), _src("/state")],  # /state repeated on purpose
    )
    assert config.all_topics() == ["/img_a", "/img_b", "/state", "/cmd"]


def test_defaults() -> None:
    config = ExportConfig(images={}, observation={}, action=[])
    assert config.fps == 0
    assert config.robot_type == "custom"
    assert config.time_range == "intersection"
