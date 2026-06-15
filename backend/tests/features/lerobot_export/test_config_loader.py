"""Tests for loading the LeRobot mapping from the active robot config."""

import pytest

from app.features.lerobot_export.config_loader import has_active_config, load_active_config, parse_config
from app.settings import RobotConfig

_VALID = {
    "fps": 20,
    "robot_type": "demo",
    "images": {"cam": "/img"},
    "observation": {"state": [{"topic": "/state", "field": "position"}]},
    "action": [{"topic": "/cmd", "field": "position", "interpolation": "nearest"}],
}


def test_has_active_config() -> None:
    assert has_active_config(RobotConfig(lerobot_export=_VALID)) is True
    assert has_active_config(RobotConfig()) is False


def test_load_active_config() -> None:
    config = load_active_config(RobotConfig(lerobot_export=_VALID))
    assert config.fps == 20
    assert config.robot_type == "demo"
    assert config.images == {"cam": "/img"}
    assert config.observation["state"][0].topic == "/state"
    assert config.action[0].interpolation == "nearest"


def test_load_active_config_not_configured() -> None:
    with pytest.raises(ValueError, match="No `lerobot_export`"):
        load_active_config(RobotConfig())


def test_load_active_config_malformed() -> None:
    with pytest.raises(ValueError, match="images"):
        load_active_config(RobotConfig(lerobot_export={"observation": {}, "action": []}))


@pytest.mark.parametrize("missing", ["images", "observation", "action"])
def test_parse_config_missing_key(missing: str) -> None:
    data = {k: v for k, v in _VALID.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        parse_config(data)


def test_parse_config_invalid_time_range() -> None:
    with pytest.raises(ValueError, match="time_range"):
        parse_config({**_VALID, "time_range": "middle"})


def test_parse_config_observation_not_a_mapping() -> None:
    # Structural error (observation is a list) must normalize to ValueError, not 500.
    with pytest.raises(ValueError, match="Malformed"):
        parse_config({**_VALID, "observation": [{"topic": "/state"}]})


def test_parse_config_source_missing_topic() -> None:
    with pytest.raises(ValueError, match="Malformed"):
        parse_config({**_VALID, "action": [{"field": "position"}]})
