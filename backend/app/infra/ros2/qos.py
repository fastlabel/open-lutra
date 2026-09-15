"""Temporary file management for QoS override YAML.

Handles creation and deletion of the QoS override file used by
ros2 bag record.
"""

import contextlib
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_TMP_DIR = Path(__file__).resolve().parent.parent.parent / "tmp"


class QoSOverrideFile:
    """Temporary file for QoS override YAML.

    Created when recording starts and removed via cleanup() when recording ends.
    """

    def __init__(self, overrides: dict[str, str]) -> None:
        _TMP_DIR.mkdir(exist_ok=True)

        # Generate YAML (reliability per topic)
        lines: list[str] = []
        for topic_name, reliability in overrides.items():
            lines.append(f"{topic_name}:")
            lines.append(f"  reliability: {reliability}")
            lines.append("  history: keep_last")
            lines.append("  depth: 10")
        yaml_content = "\n".join(lines) + "\n"

        self._file = tempfile.NamedTemporaryFile(  # noqa: SIM115
            mode="w",
            suffix=".yaml",
            prefix="qos_override_",
            dir=_TMP_DIR,
            delete=True,
        )
        self._file.write(yaml_content)
        self._file.flush()

        logger.info("Generated QoS overrides: %s\n%s", self._file.name, yaml_content)

    def to_args(self) -> list[str]:
        """Return the command-line arguments to pass to ros2 bag record."""
        return ["--qos-profile-overrides-path", self._file.name]

    def cleanup(self) -> None:
        with contextlib.suppress(Exception):
            self._file.close()
