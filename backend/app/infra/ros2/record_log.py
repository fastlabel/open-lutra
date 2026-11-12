"""Forward ros2 bag record's console output and exit status to the backend logger."""

import codecs
import logging
import re
import signal

logger = logging.getLogger(__name__)

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ROS_LEVEL = re.compile(r"^\[(DEBUG|INFO|WARN|ERROR|FATAL)\]")
_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "FATAL": logging.ERROR,
}


def describe_exit(returncode: int) -> str:
    """Name how the recorder exited: `exit code=N`, or `killed by SIGxxx` for a signal."""
    if returncode >= 0:
        return f"exit code={returncode}"
    try:
        return f"killed by {signal.Signals(-returncode).name}"
    except ValueError:
        return f"killed by signal {-returncode}"


class RecordOutputLogger:
    """Split the recorder's pty output into lines and log each at its ROS level.

    Lines without a ROS level prefix are logged as warnings: they are usually
    an uncaught C++ exception (`terminate called after throwing ...`) or a
    Python traceback, which is exactly what explains a crashed recorder.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._partial = ""

    def feed(self, data: bytes) -> None:
        """Log every complete line in `data`; keep a trailing partial line for the next call."""
        *lines, self._partial = _LINE_BREAK.split(self._partial + self._decoder.decode(data))
        for line in lines:
            self._log(line)

    def flush(self) -> None:
        """Log the trailing partial line left once the recorder has exited."""
        self._log(self._partial + self._decoder.decode(b"", final=True))
        self._partial = ""

    def _log(self, raw: str) -> None:
        line = _ANSI_ESCAPE.sub("", raw).strip()
        if not line:
            return
        match = _ROS_LEVEL.match(line)
        level = _LEVELS[match.group(1)] if match else logging.WARNING
        logger.log(level, "ros2 bag record: %s", line)
