"""Application settings powered by pydantic-settings.

Infrastructure settings are loaded from .env, while recording-specific
settings come from a YAML file (RECORDING_CONFIG).
"""

import fnmatch
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ValidatorEntry(BaseModel):
    """A single validator entry from the YAML config.

    `name` must match a builtin validator's `name` ClassVar.
    All other fields are passed as keyword arguments to the validator's constructor.
    """

    model_config = ConfigDict(extra="allow")

    name: str

    @property
    def params(self) -> dict[str, object]:
        """Extra fields forwarded to the validator constructor."""
        return self.model_extra or {}


class HzPattern(BaseModel):
    """Expected-Hz definition matched by pattern.

    When hz=None, the value is learned dynamically (computed from message
    intervals after subscription).
    """

    pattern: str
    hz: float | None = None


class MetadataFieldOption(BaseModel):
    """A single selectable value for a pre-registered metadata field.

    `value` is stored in recording_meta.json; `label` is the display text
    shown in the UI and falls back to `value` when omitted.
    """

    value: str
    label: str | None = None


class MetadataField(BaseModel):
    """A pre-registered metadata field defined by the master config.

    Operators set a value before recording; the value is written into each
    recording's recording_meta.json under `metadata` (always as a string, so
    e.g. a zero-padded operator ID like "007" keeps its leading zeros).

    `type` selects the input control:
      - "select": pick a value from `options` (required for this type).
      - "number": free numeric input restricted to digits (still stored as a
        string, preserving leading zeros).
      - "text":   free text input.
    `pattern` is an optional regex the value must match (used to flag invalid
    input in the UI). `placeholder` is an optional input hint.
    """

    key: str
    label: str
    type: Literal["select", "number", "text"] = "select"
    pattern: str | None = None
    placeholder: str | None = None
    options: list[MetadataFieldOption] = Field(default_factory=list)


class RecordingConfig(BaseModel):
    """Structure of the YAML recording configuration file."""

    robot_name: str = "Robot"
    ros_domain_id: int = 0
    recording_discovery_timeout: int = 10
    recording_start_delay_sec: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Additional seconds to wait after DDS discovery completes before "
            "sending SPACE to actually start recording. Camera drivers such as "
            "RealSense have roughly a 1-second lag between stream start and the "
            "first published frame, so waiting for that initial publish before "
            "recording eliminates the blank period at the beginning of the "
            "recording (intended for real hardware)."
        ),
    )
    monitor_qos_depth: int = 30
    default_topics: list[str] = Field(default_factory=list)
    expected_hz_patterns: list[HzPattern] = Field(default_factory=list)
    validators: list[ValidatorEntry] = Field(default_factory=list)
    metadata_fields: list[MetadataField] = Field(default_factory=list)
    stamp_quality: bool = Field(
        default=False,
        description="Compute live-quality loss_rate based on header.stamp (intended for real hardware)",
    )
    lerobot_export: dict[str, Any] | None = Field(
        default=None,
        description=(
            "LeRobot export mapping for this robot (images / observation / action / fps / ...). "
            "When omitted, the recording cannot be exported to a LeRobot dataset. "
            "See the `lerobot_export` section in config/simulator.yaml for the schema."
        ),
    )

    def resolve_expected_hz(self, topic_name: str) -> float | None:
        """Resolve the expected Hz from the pattern that matches the topic name.

        Returns the value of the first matching pattern, or None if no pattern
        matches.
        """
        for p in self.expected_hz_patterns:
            if fnmatch.fnmatch(topic_name, p.pattern):
                return p.hz
        return None


def _load_recording_config(config_path: str) -> RecordingConfig:
    """Load the recording configuration from a YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Recording configuration file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RecordingConfig.model_validate(data)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Recording configuration file path (required; must be set in .env)
    recording_config: str

    # Recording settings (required; must be set in .env)
    output_dir: Path

    # Topic monitor settings
    gap_threshold_sec: Annotated[float, Field(gt=0)] = 3.0
    monitor_buffer_size: Annotated[int, Field(ge=1)] = 600
    max_log_entries: Annotated[int, Field(ge=1)] = 500

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Upload destination selector. One destination is active per machine; see
    # docs/domain/upload.md for the extension recipe. When unset, the upload
    # feature is disabled (the /api/upload/start endpoint refuses to enqueue
    # and the UI hides its affordances).
    upload_destination: Literal["s3", "local"] | None = None

    # S3 upload destination. When either field is unset, the upload feature
    # is disabled (the /api/upload/start endpoint refuses to enqueue and the
    # UI hides its affordances).
    s3_bucket: str | None = None
    s3_key_template: str | None = None  # see app/features/upload/key_template.py

    # S3 client settings.
    #
    # Credentials are loaded from .env and forwarded to boto3 explicitly when
    # set (env-var auth). aws_session_token covers STS temporary credentials.
    # When the credential fields are unset, boto3 falls back to its own
    # discovery chain (AWS_PROFILE, shared config files, instance metadata).
    # The remaining knobs are only applied when the operator overrides the
    # boto3 defaults.
    aws_region: str | None = None
    aws_profile: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None  # for STS temporary credentials
    aws_endpoint_url: str | None = None  # e.g. http://minio:9000 for local testing
    s3_multipart_threshold_mb: int | None = None  # boto3 default: 8 MB
    s3_multipart_chunksize_mb: int | None = None  # boto3 default: 8 MB
    s3_max_concurrency: int | None = None  # boto3 default: 10

    # Local-filesystem upload destination. Intended for a local-network share
    # (NFS / SMB) bind-mounted into the backend container at
    # `local_upload_dir`. When either field is unset and
    # `upload_destination="local"`, the upload feature is disabled.
    local_upload_dir: Path | None = None
    local_upload_path_template: str | None = None  # see app/features/upload/key_template.py

    # --- Recording-specific settings loaded from YAML (cached) ---
    _recording: RecordingConfig | None = None

    @property
    def recording(self) -> RecordingConfig:
        """Return the recording configuration (loads YAML on first access)."""
        if self._recording is None:
            path = Path(self.recording_config)
            if path.exists():
                self._recording = _load_recording_config(self.recording_config)
            else:
                # Fall back to default values when the YAML does not exist (e.g. test environments)
                self._recording = RecordingConfig()
        return self._recording

    @property
    def ros_domain_id(self) -> int:
        """ROS2 domain ID."""
        return self.recording.ros_domain_id

    @property
    def recording_discovery_timeout(self) -> int:
        """Maximum seconds to wait for DDS discovery when starting a recording."""
        return self.recording.recording_discovery_timeout

    @property
    def recording_start_delay_sec(self) -> float:
        """Additional seconds to wait after DDS discovery completes before sending SPACE."""
        return self.recording.recording_start_delay_sec

    @property
    def monitor_qos_depth(self) -> int:
        """QoS queue depth for topic-monitor subscriptions."""
        return self.recording.monitor_qos_depth

    @property
    def robot_name(self) -> str:
        """Robot name shown in the UI status bar."""
        return self.recording.robot_name

    @property
    def default_topics(self) -> list[str]:
        """Default list of topic names to record."""
        return self.recording.default_topics

    @property
    def stamp_quality(self) -> bool:
        """Whether to compute live-quality loss_rate based on header.stamp."""
        return self.recording.stamp_quality

    @property
    def metadata_fields(self) -> list[MetadataField]:
        """Master-defined metadata fields offered before recording."""
        return self.recording.metadata_fields


def get_settings() -> Settings:
    """Return application settings (lru_cache is intentionally not used for testability)."""
    return Settings()
