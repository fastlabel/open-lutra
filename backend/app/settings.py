"""Application settings powered by pydantic-settings.

Infrastructure settings are loaded from .env, while robot-specific settings come
from a YAML file (ROBOT_CONFIG).
"""

import fnmatch
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HzPattern(BaseModel):
    """Expected-Hz definition matched by pattern.

    When hz=None, the value is learned dynamically (computed from message
    intervals after subscription).
    """

    pattern: str
    hz: float | None = None


class RobotConfig(BaseModel):
    """Structure of the YAML robot configuration file."""

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


def _load_robot_config(config_path: str) -> RobotConfig:
    """Load the robot configuration from a YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Robot configuration file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RobotConfig.model_validate(data)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Robot configuration file path (required; must be set in .env)
    robot_config: str

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

    # S3 upload destination. When either field is unset, the upload feature
    # is disabled (the eventual /api/upload/start endpoint refuses to enqueue
    # and the UI hides its affordances).
    s3_bucket: str | None = None
    s3_key_template: str | None = None  # see app/features/upload/key_template.py

    # S3 client settings.
    #
    # Credentials are NOT declared here — boto3 picks AWS_ACCESS_KEY_ID /
    # AWS_SECRET_ACCESS_KEY (or AWS_PROFILE) directly from the process env.
    # Declaring them in pydantic would shadow that lookup. The remaining knobs
    # are only set when the operator overrides the boto3 defaults.
    aws_region: str | None = None
    aws_profile: str | None = None
    aws_endpoint_url: str | None = None  # e.g. http://minio:9000 for local testing
    s3_multipart_threshold_mb: int | None = None  # boto3 default: 8 MB
    s3_multipart_chunksize_mb: int | None = None  # boto3 default: 8 MB
    s3_max_concurrency: int | None = None  # boto3 default: 10

    # --- Robot-specific settings loaded from YAML (cached) ---
    _robot: RobotConfig | None = None

    @property
    def robot(self) -> RobotConfig:
        """Return the robot configuration (loads YAML on first access)."""
        if self._robot is None:
            path = Path(self.robot_config)
            if path.exists():
                self._robot = _load_robot_config(self.robot_config)
            else:
                # Fall back to default values when the YAML does not exist (e.g. test environments)
                self._robot = RobotConfig()
        return self._robot

    @property
    def ros_domain_id(self) -> int:
        """ROS2 domain ID."""
        return self.robot.ros_domain_id

    @property
    def recording_discovery_timeout(self) -> int:
        """Maximum seconds to wait for DDS discovery when starting a recording."""
        return self.robot.recording_discovery_timeout

    @property
    def recording_start_delay_sec(self) -> float:
        """Additional seconds to wait after DDS discovery completes before sending SPACE."""
        return self.robot.recording_start_delay_sec

    @property
    def monitor_qos_depth(self) -> int:
        """QoS queue depth for topic-monitor subscriptions."""
        return self.robot.monitor_qos_depth

    @property
    def robot_name(self) -> str:
        """Robot name shown in the UI status bar."""
        return self.robot.robot_name

    @property
    def default_topics(self) -> list[str]:
        """Default list of topic names to record."""
        return self.robot.default_topics

    @property
    def stamp_quality(self) -> bool:
        """Whether to compute live-quality loss_rate based on header.stamp."""
        return self.robot.stamp_quality


def get_settings() -> Settings:
    """Return application settings (lru_cache is intentionally not used for testability)."""
    return Settings()
