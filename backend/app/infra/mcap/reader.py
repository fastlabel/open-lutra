"""Unified MCAP file reader.

Encapsulates the boilerplate of initializing the `mcap` + `mcap_ros2`
libraries and normalizes messages into the units used by the features
layer (MCAPMessage / MCAPChannel).

Use as a context manager:

    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages(topics=["/joint_states"]):
            process(msg.decoded, msg.timestamp_ns)
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO, Any

from mcap.exceptions import McapError
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory


class CorruptedMCAPError(Exception):
    """An MCAP file could not be parsed.

    Raised in place of the mcap library's low-level parse errors so that the
    message names the file and the typical causes (a recording cut short —
    full disk, power loss, or a force-killed recorder — truncates the MCAP
    mid-record).
    """

    @classmethod
    def from_cause(cls, path: Path, cause: Exception) -> "CorruptedMCAPError":
        """Build the user-facing error from a low-level mcap parse error."""
        detail = str(cause) or cause.__class__.__name__
        return cls(
            f"MCAP file is unreadable (truncated or corrupted): {path.name} — {detail}. "
            "This usually means the recording was cut short — e.g. the disk filled up, "
            "the machine lost power, or the recorder was forcibly killed."
        )


@dataclass(frozen=True)
class MCAPChannel:
    """MCAP channel info (topic, msg_type)."""

    topic: str
    msg_type: str


@dataclass
class MCAPMessage:
    """A single decoded message.

    Attributes:
        topic: Topic name.
        msg_type: ROS2 message type name (e.g., `sensor_msgs/msg/JointState`).
        timestamp_ns: MCAP `log_time` in nanoseconds. To use `header.stamp`
            instead, callers should call `resolve_timestamp_ns(decoded, timestamp_ns)`.
        decoded: ROS2 message object (dynamic type, no rclpy dependency).
        size_bytes: Binary size of the original message.
    """

    topic: str
    msg_type: str
    timestamp_ns: int
    decoded: Any
    size_bytes: int


class MCAPReader:
    """Unified MCAP file reader (context manager).

    Hides initialization of `mcap.reader.make_reader` + `mcap_ros2.DecoderFactory`
    so that features only need to worry about iterating MCAPMessage values.
    """

    def __init__(self, path: Path) -> None:  # pragma: no cover - MCAP I/O boundary
        self._path = path
        self._file: IO[bytes] | None = None
        self._reader: Any = None  # mcap.reader.McapReader (typed as Any since it lives in the mcap library)

    def __enter__(self) -> "MCAPReader":  # pragma: no cover - MCAP I/O boundary
        self._file = self._path.open("rb")
        try:
            self._reader = make_reader(self._file, decoder_factories=[DecoderFactory()])
        except McapError as e:
            # e.g. EndOfFile (empty message) for a 0-byte file left by a recorder
            # that could not write anything.
            self._file.close()
            self._file = None
            raise CorruptedMCAPError.from_cause(self._path, e) from e
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:  # pragma: no cover - MCAP I/O boundary
        if self._file is not None:
            self._file.close()
            self._file = None
            self._reader = None

    def get_channels(self) -> dict[str, MCAPChannel]:  # pragma: no cover - MCAP I/O boundary
        """Return a topic → MCAPChannel dict (from the MCAP summary).

        Returns an empty dict if no summary exists (old or truncated MCAP).
        """
        assert self._reader is not None, "MCAPReader must be used as a context manager"
        summary = self._get_summary()
        if summary is None or not summary.channels or not summary.schemas:
            return {}
        channels: dict[str, MCAPChannel] = {}
        for channel in summary.channels.values():
            schema = summary.schemas.get(channel.schema_id)
            channels[channel.topic] = MCAPChannel(
                topic=channel.topic,
                msg_type=schema.name if schema else "unknown",
            )
        return channels

    def get_time_range_ns(self) -> tuple[int, int]:  # pragma: no cover - MCAP I/O boundary
        """Return the overall log_time range of the MCAP as (start_ns, end_ns).

        Returns (0, 0) if no summary exists.
        """
        assert self._reader is not None, "MCAPReader must be used as a context manager"
        summary = self._get_summary()
        if summary is None or summary.statistics is None:
            return (0, 0)
        stats = summary.statistics
        return (stats.message_start_time, stats.message_end_time)

    def iter_messages(
        self,
        *,
        topics: list[str] | None = None,
        start_time_ns: int | None = None,
        end_time_ns: int | None = None,
    ) -> Iterator[MCAPMessage]:  # pragma: no cover - MCAP I/O boundary
        """Iterate messages and yield decoded MCAPMessage values.

        The topic and time-range filters are applied at the chunk index level,
        so this stays fast even for large MCAPs.

        Args:
            topics: Topic names to filter to (None for all topics).
            start_time_ns: Inclusive lower bound on log_time.
            end_time_ns: Inclusive upper bound on log_time.
        """
        assert self._reader is not None, "MCAPReader must be used as a context manager"
        iterator = self._reader.iter_decoded_messages(
            topics=topics,
            start_time=start_time_ns,
            end_time=end_time_ns,
        )
        try:
            for schema, channel, message, decoded in iterator:
                yield MCAPMessage(
                    topic=channel.topic,
                    msg_type=schema.name if schema else "unknown",
                    timestamp_ns=message.log_time,
                    decoded=decoded,
                    size_bytes=len(message.data),
                )
        except McapError as e:
            raise CorruptedMCAPError.from_cause(self._path, e) from e

    def _get_summary(self) -> Any:  # pragma: no cover - MCAP I/O boundary
        """Read the MCAP summary, translating parse errors of corrupt files."""
        try:
            return self._reader.get_summary()
        except McapError as e:
            raise CorruptedMCAPError.from_cause(self._path, e) from e


def find_mcap_files(folder: Path) -> list[Path]:
    """Return `*.mcap` files in a recording folder.

    Recordings are expected not to be split, but by design all files are
    returned if multiple exist. sorted() yields filenames (recording_id_seq)
    in ascending order.
    """
    return sorted(folder.glob("*.mcap"))
