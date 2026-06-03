"""Tests for active_set."""

from pathlib import Path

import pytest

from app.features.validation.active_set import get_builtin_recording_validators
from app.features.validation.builtins import RequiredTopicsPresent, TotalDurationSec
from app.settings import Settings


def _settings_with_yaml(tmp_path: Path, content: str) -> Settings:
    yaml_path = tmp_path / "robot.yaml"
    yaml_path.write_text(content, encoding="utf-8")
    return Settings(robot_config=str(yaml_path))


class TestGetBuiltinRecordingValidators:
    def test_empty_validators_returns_empty_list(self, tmp_path: Path) -> None:
        s = Settings(robot_config=str(tmp_path / "missing.yaml"))
        assert get_builtin_recording_validators(s) == []

    def test_required_topics_present(self, tmp_path: Path) -> None:
        s = _settings_with_yaml(
            tmp_path,
            "validators:\n"
            "  - name: required_topics_present\n"
            "    topics:\n"
            "      - /foo\n"
            "      - /bar\n",
        )
        validators = get_builtin_recording_validators(s)
        assert len(validators) == 1
        assert isinstance(validators[0], RequiredTopicsPresent)
        assert validators[0].topics == ["/foo", "/bar"]

    def test_total_duration_sec(self, tmp_path: Path) -> None:
        s = _settings_with_yaml(
            tmp_path,
            "validators:\n"
            "  - name: total_duration_sec\n"
            "    min_sec: 5\n"
            "    max_sec: 30\n",
        )
        validators = get_builtin_recording_validators(s)
        assert len(validators) == 1
        assert isinstance(validators[0], TotalDurationSec)
        assert validators[0].min_sec == 5.0
        assert validators[0].max_sec == 30.0

    def test_both_builtins(self, tmp_path: Path) -> None:
        s = _settings_with_yaml(
            tmp_path,
            "validators:\n"
            "  - name: required_topics_present\n"
            "    topics: [/cam]\n"
            "  - name: total_duration_sec\n"
            "    min_sec: 5\n",
        )
        validators = get_builtin_recording_validators(s)
        types = {type(v) for v in validators}
        assert RequiredTopicsPresent in types
        assert TotalDurationSec in types

    def test_returns_new_instances_each_call(self, tmp_path: Path) -> None:
        s = _settings_with_yaml(
            tmp_path,
            "validators:\n  - name: total_duration_sec\n    min_sec: 5\n",
        )
        a = get_builtin_recording_validators(s)
        b = get_builtin_recording_validators(s)
        assert a is not b
        assert all(x is not y for x, y in zip(a, b, strict=True))

    def test_unknown_validator_name_raises(self, tmp_path: Path) -> None:
        s = _settings_with_yaml(
            tmp_path,
            "validators:\n  - name: nonexistent_validator\n",
        )
        with pytest.raises(ValueError, match="nonexistent_validator"):
            get_builtin_recording_validators(s)
