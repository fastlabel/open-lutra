"""Domain models for the media feature (topic classification/mapping for MP4 / telemetry.json conversion).

Used by `mcap_converter.py` when generating MP4 / telemetry.json:
  - Deriving camera name / joint prefix from topic name
  - Classifying JointState topics as observation/action
  - Determining a stable sort order
"""

from dataclasses import dataclass
from enum import Enum


class MediaError(Exception):
    """Base exception for MP4 / telemetry.json conversion."""


class MissingTopicError(MediaError):
    """Raised when a required topic (camera or JointState) is not in the MCAP."""


class TopicRole(Enum):
    """Role of a JointState topic."""

    OBSERVATION = "observation"
    ACTION = "action"


# --- Automatic role detection from topic name ---

_OBSERVATION_KEYWORDS = ("state", "states", "status", "feedback", "slave", "body")
_ACTION_KEYWORDS = ("cmd", "command", "target", "goal", "master")


def _tokenize_topic(topic_name: str) -> list[str]:
    """Split a topic name on both "/" and "_" and return the token list.

    Example: "/mcap/slave_arm_right" -> ["", "mcap", "slave", "arm", "right"]
    """
    return topic_name.lower().replace("_", "/").split("/")


def classify_joint_state_topic(topic_name: str) -> TopicRole | None:
    """Infer the observation/action role from a JointState topic name.

    Splits the topic name on "/" and "_" and checks whether each token
    matches a keyword. Returns None if the role cannot be determined.

    Args:
        topic_name: ROS2 topic name (e.g. "/mcap/slave_arm_right").

    Returns:
        The inferred role, or None if it cannot be determined.
    """
    tokens = _tokenize_topic(topic_name)
    for token in tokens:
        if any(kw == token for kw in _ACTION_KEYWORDS):
            return TopicRole.ACTION
        if any(kw == token for kw in _OBSERVATION_KEYWORDS):
            return TopicRole.OBSERVATION
    return None


def derive_camera_name(topic_name: str) -> str:
    """Derive the camera name from a ROS2 topic name.

    Uses the first segment after stripping the leading "/" as the camera name.
    Example: "/right_arm_depth_cam/color/image_raw/compressed" -> "right_arm_depth_cam"
    """
    stripped = topic_name.lstrip("/")
    return stripped.split("/")[0] if stripped else topic_name


# --- Joint topic mapping ---


def derive_joint_prefix(topic_name: str) -> str:
    """Derive the URDF joint name prefix from a topic name.

    Topic containing "right" -> "R_"
    Topic containing "left"  -> "L_"
    Otherwise (body, etc.)   -> ""
    """
    lower = topic_name.lower()
    if "right" in lower:
        return "R_"
    if "left" in lower:
        return "L_"
    return ""


def _derive_sort_key(topic_name: str) -> tuple[int, str]:
    """Derive a stable sort key from a topic name.

    Priority order: right(0) -> left(1) -> body(2) -> other(3).
    Placing body last keeps arm indices stable starting from the front
    even in simulator environments that have no body data.
    Within the same category, sort by topic name lexicographically so the
    order is preserved across topic additions, removals, and re-additions.
    """
    lower = topic_name.lower()
    if "right" in lower:
        return (0, topic_name)
    if "left" in lower:
        return (1, topic_name)
    if "body" in lower:
        return (2, topic_name)
    return (3, topic_name)


@dataclass(frozen=True)
class JointTopicEntry:
    """Mapping info for a single joint topic."""

    topic: str
    joint_prefix: str  # "R_", "L_", "" (body, etc.)


@dataclass(frozen=True)
class JointStateMapping:
    """Mapping between JointState topics and telemetry.json fields.

    Holds multiple observation/action topics in a stable order.
    """

    observation_entries: tuple[JointTopicEntry, ...]
    action_entries: tuple[JointTopicEntry, ...]

    @property
    def observation_topics(self) -> list[str]:
        """List of observation topic names (sorted)."""
        return [e.topic for e in self.observation_entries]

    @property
    def action_topics(self) -> list[str]:
        """List of action topic names (sorted)."""
        return [e.topic for e in self.action_entries]


def build_joint_state_mapping(topic_roles: dict[str, str]) -> JointStateMapping | None:
    """Build a mapping from a set of JointState topics.

    Classifies multiple observation/action topics and sorts them in a stable
    order (body -> right -> left -> other). The order is preserved across
    topic additions, removals, and re-additions.

    Args:
        topic_roles: Dict of {topic name: message type name}. Must contain
            only JointState topics.

    Returns:
        The mapping, or None if there are no JointState topics.
    """
    if not topic_roles:
        return None

    obs_entries: list[JointTopicEntry] = []
    act_entries: list[JointTopicEntry] = []
    unclassified_entries: list[JointTopicEntry] = []

    for topic in topic_roles:
        role = classify_joint_state_topic(topic)
        prefix = derive_joint_prefix(topic)
        entry = JointTopicEntry(topic=topic, joint_prefix=prefix)

        if role == TopicRole.OBSERVATION:
            obs_entries.append(entry)
        elif role == TopicRole.ACTION:
            act_entries.append(entry)
        else:
            unclassified_entries.append(entry)

    # Use unclassified topics as a fallback
    if not obs_entries and not act_entries:
        obs_entries = list(unclassified_entries)
    elif not obs_entries:
        obs_entries = list(unclassified_entries) if unclassified_entries else list(act_entries)
    elif not act_entries:
        act_entries = list(unclassified_entries) if unclassified_entries else list(obs_entries)

    if not obs_entries:  # pragma: no cover - defensive; unreachable once topic_roles is non-empty
        return None

    # Stable sort: right(0) -> left(1) -> body(2) -> other(3)
    obs_entries.sort(key=lambda e: _derive_sort_key(e.topic))
    act_entries.sort(key=lambda e: _derive_sort_key(e.topic))

    return JointStateMapping(
        observation_entries=tuple(obs_entries),
        action_entries=tuple(act_entries),
    )
