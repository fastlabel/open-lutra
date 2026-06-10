"""Domain models for LeRobot dataset export.

These mirror the JSON mapping-config shape (see `config/lerobot/*.json`) that
declares how MCAP topics map to LeRobot `observation.*` / `action` / image
features. Kept separate from API schemas (schemas.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_INTERPOLATION = "linear"
DEFAULT_SYNC_TOLERANCE_MS = 50.0
DEFAULT_IMAGE_TOLERANCE_MS = 200.0
DEFAULT_TIME_RANGE = "intersection"


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """One data source feeding an observation field or the action vector.

    Attributes:
        topic: ROS2 topic name.
        field: Attribute to extract. None uses the sensor's default for the
            topic's message type (e.g. `position` for JointState, `data` for
            Float*MultiArray); set it to override (e.g. `velocity`).
        indices: Indices to keep (None = all).
        names: Per-dimension labels recorded into info.json (None = auto).
        interpolation: "linear" or "nearest".
    """

    topic: str
    field: str | None = None
    indices: list[int] | None = None
    names: list[str] | None = None
    interpolation: str = DEFAULT_INTERPOLATION


@dataclass(frozen=True, slots=True)
class ExportConfig:
    """Full mapping configuration for one export.

    Attributes:
        images: {camera_name: topic} for `observation.images.<camera_name>`.
        observation: {field_name: [SourceConfig, ...]} for `observation.<field_name>`.
        action: [SourceConfig, ...] concatenated into the `action` vector.
        fps: Output frame rate (0 = auto-detect from the first image topic).
        robot_type: Free-form robot identifier stored in info.json.
        sync_tolerance_ms: Time-sync tolerance for state/action sources.
        image_tolerance_ms: Time-sync tolerance for image alignment.
        time_range: "intersection" or "union" for the per-recording timebase.

    One recording is always exported as exactly one episode.
    """

    images: dict[str, str]
    observation: dict[str, list[SourceConfig]]
    action: list[SourceConfig]
    fps: int = 0
    robot_type: str = "custom"
    sync_tolerance_ms: float = DEFAULT_SYNC_TOLERANCE_MS
    image_tolerance_ms: float = DEFAULT_IMAGE_TOLERANCE_MS
    time_range: str = DEFAULT_TIME_RANGE

    def all_topics(self) -> list[str]:
        """Return the de-duplicated set of every topic referenced by the config."""
        topics: list[str] = list(self.images.values())
        for sources in self.observation.values():
            topics.extend(src.topic for src in sources)
        topics.extend(src.topic for src in self.action)
        # Preserve first-seen order while de-duplicating.
        seen: set[str] = set()
        unique: list[str] = []
        for topic in topics:
            if topic not in seen:
                seen.add(topic)
                unique.append(topic)
        return unique


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """Resolved feature shapes/names probed from the first MCAP.

    Attributes:
        camera_names: Ordered camera names (= info.json image feature suffixes).
        image_shapes: {camera_name: (height, width, channels)}.
        observation_fields: {field_name: (dim, names)}.
        action_dim: Length of the action vector.
        action_names: Per-dimension labels for the action vector.
    """

    camera_names: list[str]
    image_shapes: dict[str, tuple[int, int, int]]
    observation_fields: dict[str, tuple[int, list[str]]]
    action_dim: int
    action_names: list[str] = field(default_factory=list)
