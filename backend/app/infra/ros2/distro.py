"""Differences between the supported ROS 2 distros.

Every distro-dependent detail of the `ros2` CLI lives here; callers obtain the
running distro with `current_distro()` and never branch on its name.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RosDistro:
    name: str
    # Flag preceding the topic list of `ros2 bag record`; None means positional
    topics_flag: str | None
    # Log line `ros2 bag record --start-paused` prints once it accepts the SPACE key
    start_prompt: str

    def topic_args(self, topics: list[str]) -> list[str]:
        """Topic arguments for `ros2 bag record`."""
        return [self.topics_flag, *topics] if self.topics_flag else list(topics)


HUMBLE = RosDistro(name="humble", topics_flag=None, start_prompt="Waiting for recording: Press")
JAZZY = RosDistro(name="jazzy", topics_flag="--topics", start_prompt="Wait for recording: Press")

_SUPPORTED = {d.name: d for d in (HUMBLE, JAZZY)}


def current_distro() -> RosDistro:
    """The distro of the sourced ROS 2 environment (`ROS_DISTRO`, set by the base image).

    Raises:
        ValueError: If `ROS_DISTRO` is unset or not a supported distro.
    """
    name = os.environ.get("ROS_DISTRO", "")
    try:
        return _SUPPORTED[name]
    except KeyError:
        raise ValueError(f"Unsupported ROS_DISTRO {name!r}; supported: {', '.join(_SUPPORTED)}") from None
