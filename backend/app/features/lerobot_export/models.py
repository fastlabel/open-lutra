"""Domain models for LeRobot dataset export.

These mirror the JSON mapping-config shape (see `config/lerobot/*.json`) that
declares how MCAP topics map to LeRobot `observation.*` / `action` / image
features. Kept separate from API schemas (schemas.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DEFAULT_INTERPOLATION = "linear"
DEFAULT_SYNC_TOLERANCE_MS = 50.0
DEFAULT_IMAGE_TOLERANCE_MS = 200.0
DEFAULT_TIME_RANGE = "intersection"


FieldType = Literal["list", "number", "struct"]


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """One data source feeding an observation field or the action vector.

    Attributes:
        topic: ROS2 topic name.
        field: Dot-separated attribute path to extract (e.g.
            "joint_state.position", "gripper_pos", "pose.position"). None
            means apply extraction directly to the decoded message itself
            (used for struct types where the top-level message is the target,
            e.g. geometry_msgs/Point published as a standalone topic).
        type: Value type at the resolved path.
            - "list": numeric sequence; `indices` is required.
            - "number": scalar float/int; wrapped as a 1-element array.
            - "struct": named-field object (e.g. geometry_msgs/Point);
              `keys` is required. `field` may be None.
        indices: Elements to keep (required when type == "list"); out-of-range
            indices are filled with 0.0 to keep a fixed-length vector.
        keys: Attribute names to extract in order (required when
            type == "struct").
        names: Per-dimension labels recorded into info.json (None = auto).
        interpolation: "linear" or "nearest".
    """

    topic: str
    field: str | None
    type: FieldType
    indices: list[int] | None = None
    keys: list[str] | None = None
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
