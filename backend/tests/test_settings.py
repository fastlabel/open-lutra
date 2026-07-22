"""Tests for application settings (Settings / RecordingConfig)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import (
    HzPattern,
    MetadataField,
    RecordingConfig,
    Settings,
    ValidatorEntry,
    _load_recording_config,
    get_settings,
)

# ---------------------------------------------------------------------------
# RecordingConfig
# ---------------------------------------------------------------------------


class TestRecordingConfig:
    """Tests for RecordingConfig defaults and validation."""

    def test_defaults(self) -> None:
        """All fields have a default value defined."""
        cfg = RecordingConfig()
        assert cfg.robot_name == "Robot"
        assert cfg.ros_domain_id == 0
        assert cfg.recording_discovery_timeout == 10
        assert cfg.recording_start_delay_sec == 0.0
        assert cfg.monitor_qos_depth == 30
        assert cfg.default_topics == []
        assert cfg.expected_hz_patterns == []
        assert cfg.stamp_quality is False
        assert cfg.validators == []
        assert cfg.metadata_fields == []

    def test_recording_start_delay_sec_negative_rejected(self) -> None:
        """Negative start_delay_sec is rejected by the ge=0 constraint."""
        with pytest.raises(ValueError):
            RecordingConfig(recording_start_delay_sec=-1.0)

    def test_recording_start_delay_sec_zero_allowed(self) -> None:
        """Zero is allowed."""
        cfg = RecordingConfig(recording_start_delay_sec=0.0)
        assert cfg.recording_start_delay_sec == 0.0

    def test_recording_start_delay_sec_positive(self) -> None:
        """Positive values are preserved as-is."""
        cfg = RecordingConfig(recording_start_delay_sec=2.5)
        assert cfg.recording_start_delay_sec == 2.5


class TestMetadataField:
    """Tests for MetadataField config validation."""

    def test_select_without_options_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """A select field with no options logs a non-blocking warning (still constructs)."""
        with caplog.at_level("WARNING"):
            field = MetadataField(key="target_object", label="Target Object", type="select")
        assert field.type == "select"
        assert "has no options" in caplog.text
        assert "target_object" in caplog.text

    def test_select_with_options_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """A select field with options does not warn."""
        from app.settings import MetadataFieldOption

        with caplog.at_level("WARNING"):
            MetadataField(key="k", label="L", type="select", options=[MetadataFieldOption(value="a")])
        assert caplog.text == ""

    def test_number_without_options_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """Non-select fields legitimately have no options and must not warn."""
        with caplog.at_level("WARNING"):
            MetadataField(key="operator_id", label="Operator ID", type="number")
        assert caplog.text == ""


class TestResolveExpectedHz:
    """Tests for RecordingConfig.resolve_expected_hz()."""

    def test_no_patterns(self) -> None:
        """No patterns returns None."""
        cfg = RecordingConfig()
        assert cfg.resolve_expected_hz("/foo") is None

    def test_glob_match(self) -> None:
        """Returns the Hz of the first matching glob pattern."""
        cfg = RecordingConfig(
            expected_hz_patterns=[
                HzPattern(pattern="**/compressed", hz=30.0),
                HzPattern(pattern="/joint/*", hz=200.0),
            ]
        )
        assert cfg.resolve_expected_hz("/cam/image/compressed") == 30.0
        assert cfg.resolve_expected_hz("/joint/state") == 200.0

    def test_first_match_wins(self) -> None:
        """When multiple patterns match, the first one takes precedence."""
        cfg = RecordingConfig(
            expected_hz_patterns=[
                HzPattern(pattern="/foo/*", hz=10.0),
                HzPattern(pattern="/foo/bar", hz=20.0),
            ]
        )
        assert cfg.resolve_expected_hz("/foo/bar") == 10.0

    def test_dynamic_learning_returns_none_hz(self) -> None:
        """A pattern with hz explicitly set to None returns None (dynamic learning)."""
        cfg = RecordingConfig(expected_hz_patterns=[HzPattern(pattern="/sensor/*", hz=None)])
        assert cfg.resolve_expected_hz("/sensor/imu") is None

    def test_no_match(self) -> None:
        """No match returns None."""
        cfg = RecordingConfig(expected_hz_patterns=[HzPattern(pattern="/foo/*", hz=30.0)])
        assert cfg.resolve_expected_hz("/bar") is None


# ---------------------------------------------------------------------------
# _load_recording_config
# ---------------------------------------------------------------------------


class TestLoadRecordingConfig:
    """Tests for _load_recording_config()."""

    def test_loads_yaml(self, tmp_path: Path) -> None:
        """Loads a valid YAML file."""
        yaml_path = tmp_path / "recording.yaml"
        yaml_path.write_text(
            """
robot_name: TestBot
ros_domain_id: 7
recording_discovery_timeout: 5
recording_start_delay_sec: 1.5
default_topics:
  - /joint
expected_hz_patterns:
  - pattern: "**/compressed"
    hz: 30
""",
            encoding="utf-8",
        )
        cfg = _load_recording_config(str(yaml_path))
        assert cfg.robot_name == "TestBot"
        assert cfg.ros_domain_id == 7
        assert cfg.recording_discovery_timeout == 5
        assert cfg.recording_start_delay_sec == 1.5
        assert cfg.default_topics == ["/joint"]
        assert cfg.expected_hz_patterns[0].pattern == "**/compressed"
        assert cfg.expected_hz_patterns[0].hz == 30.0

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when the file does not exist."""
        with pytest.raises(FileNotFoundError):
            _load_recording_config(str(tmp_path / "nonexistent.yaml"))


# ---------------------------------------------------------------------------
# ValidatorEntry
# ---------------------------------------------------------------------------


class TestValidatorEntry:
    """Tests for ValidatorEntry model."""

    def test_name_only(self) -> None:
        entry = ValidatorEntry(name="total_duration_sec")
        assert entry.name == "total_duration_sec"
        assert entry.params == {}

    def test_extra_fields_become_params(self) -> None:
        entry = ValidatorEntry(name="required_topics_present", topics=["/foo", "/bar"])
        assert entry.params == {"topics": ["/foo", "/bar"]}

    def test_multiple_extra_fields(self) -> None:
        entry = ValidatorEntry(name="total_duration_sec", min_sec=5.0, max_sec=30.0)
        assert entry.params == {"min_sec": 5.0, "max_sec": 30.0}


class TestRecordingConfigValidators:
    """Tests for the validators field on RecordingConfig."""

    def test_loaded_from_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "recording.yaml"
        yaml_path.write_text(
            "validators:\n"
            "  - name: required_topics_present\n"
            "    topics:\n"
            "      - /cam\n"
            "  - name: total_duration_sec\n"
            "    min_sec: 5\n"
            "    max_sec: 30\n",
            encoding="utf-8",
        )
        cfg = _load_recording_config(str(yaml_path))
        assert len(cfg.validators) == 2
        assert cfg.validators[0].name == "required_topics_present"
        assert cfg.validators[0].params == {"topics": ["/cam"]}
        assert cfg.validators[1].name == "total_duration_sec"
        assert cfg.validators[1].params == {"min_sec": 5, "max_sec": 30}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestSettings:
    """Tests for the Settings class."""

    def test_recording_uses_default_when_yaml_missing(self, tmp_path: Path) -> None:
        """Returns the default RecordingConfig when the YAML file does not exist."""
        s = Settings(recording_config=str(tmp_path / "missing.yaml"), output_dir=tmp_path)
        recording = s.recording
        assert recording.robot_name == "Robot"
        assert recording.ros_domain_id == 0

    def test_recording_loads_yaml(self, tmp_path: Path) -> None:
        """Loads the YAML file when one is present."""
        yaml_path = tmp_path / "recording.yaml"
        yaml_path.write_text(
            "robot_name: MyBot\nros_domain_id: 99\nrecording_start_delay_sec: 2.0\n",
            encoding="utf-8",
        )
        s = Settings(recording_config=str(yaml_path), output_dir=tmp_path)
        assert s.recording.robot_name == "MyBot"
        assert s.recording.ros_domain_id == 99

    def test_recording_is_cached(self, tmp_path: Path) -> None:
        """The recording property is loaded only on first access (cached)."""
        yaml_path = tmp_path / "recording.yaml"
        yaml_path.write_text("robot_name: Cached\n", encoding="utf-8")
        s = Settings(recording_config=str(yaml_path), output_dir=tmp_path)
        first = s.recording
        second = s.recording
        assert first is second  # Same instance

    def test_property_passthroughs(self, tmp_path: Path) -> None:
        """Each property returns the corresponding RecordingConfig value."""
        yaml_path = tmp_path / "recording.yaml"
        yaml_path.write_text(
            """
robot_name: PropTest
ros_domain_id: 42
recording_discovery_timeout: 8
recording_start_delay_sec: 3.5
monitor_qos_depth: 50
default_topics:
  - /a
  - /b
stamp_quality: true
expected_hz_patterns:
  - pattern: "/a"
    hz: 100
metadata_fields:
  - key: operator_id
    label: Operator ID
    type: number
    pattern: '^[0-9]+$'
    placeholder: "e.g. 007"
  - key: target_object
    label: Target Object
    options:
      - value: box
        label: "Box"
      - value: cup
""",
            encoding="utf-8",
        )
        s = Settings(recording_config=str(yaml_path), output_dir=tmp_path)
        assert s.robot_name == "PropTest"
        assert s.ros_domain_id == 42
        assert s.recording_discovery_timeout == 8
        assert s.recording_start_delay_sec == 3.5
        assert s.monitor_qos_depth == 50
        assert s.default_topics == ["/a", "/b"]
        assert s.stamp_quality is True
        assert len(s.metadata_fields) == 2
        # A number field: explicit type / pattern / placeholder, no options.
        operator = s.metadata_fields[0]
        assert operator.key == "operator_id"
        assert operator.label == "Operator ID"
        assert operator.type == "number"
        assert operator.pattern == "^[0-9]+$"
        assert operator.placeholder == "e.g. 007"
        assert operator.options == []
        # A select field: type defaults to "select"; pattern / placeholder default to None.
        target = s.metadata_fields[1]
        assert target.type == "select"
        assert target.pattern is None
        assert target.placeholder is None
        assert target.options[0].value == "box"
        assert target.options[0].label == "Box"
        # Option label is optional in the master config (falls back to value at the API layer).
        assert target.options[1].value == "cup"
        assert target.options[1].label is None

    def test_recording_start_delay_sec_default(self, tmp_path: Path) -> None:
        """Defaults to 0.0 when not specified in YAML."""
        yaml_path = tmp_path / "recording.yaml"
        yaml_path.write_text("robot_name: Foo\n", encoding="utf-8")
        s = Settings(recording_config=str(yaml_path), output_dir=tmp_path)
        assert s.recording_start_delay_sec == 0.0

    def test_missing_recording_config_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Raises ValidationError when RECORDING_CONFIG is not set."""
        monkeypatch.delenv("RECORDING_CONFIG", raising=False)
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        with pytest.raises(ValidationError, match="recording_config"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_missing_output_dir_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ValidationError when OUTPUT_DIR is not set."""
        monkeypatch.setenv("RECORDING_CONFIG", "config/simulator.yaml")
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        with pytest.raises(ValidationError, match="output_dir"):
            Settings(_env_file=None)  # type: ignore[call-arg]


class TestGetSettings:
    """Tests for get_settings()."""

    def test_returns_settings_instance(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Returns a Settings instance."""
        monkeypatch.setenv("RECORDING_CONFIG", "config/simulator.yaml")
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        s = get_settings()
        assert isinstance(s, Settings)
