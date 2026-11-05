"""Decide which encoder a video job actually uses.

`VIDEO_ENCODER=nvenc` only expresses intent: the container may still lack a GPU
(started without the GPU compose override), the driver may lack NVENC, or the
GPU may be briefly unavailable (driver still initializing, every encoder session
taken). A one-frame probe settles it before a job starts, so a host that cannot
use NVENC goes straight to the CPU instead of failing every encode first.

A successful probe is remembered for the rest of the process; a failed one is
retried before the next job, so a transient failure does not disable the GPU
until the backend restarts. The warning is logged once per run of failures.
"""

import logging
import subprocess
import threading

from app.infra.video.commands import VideoEncoder, nvenc_probe_command

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SEC = 30


class _ProbeState:
    """Probe outcome shared by all jobs of this process."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.confirmed = False
        self.warned = False


_state = _ProbeState()


def resolve_encoder(requested: VideoEncoder, nvenc_usable: bool) -> VideoEncoder:
    """Return the encoder to use given the setting and whether NVENC passed its probe."""
    if requested == "nvenc" and not nvenc_usable:
        return "libx264"
    return requested


def effective_encoder(requested: VideoEncoder) -> VideoEncoder:  # pragma: no cover - runs ffmpeg
    """Resolve the configured encoder for one job, probing NVENC only when it is requested."""
    if requested == "nvenc":
        return resolve_encoder(requested, nvenc_usable())
    return requested


def nvenc_usable() -> bool:  # pragma: no cover - runs ffmpeg
    """Whether NVENC works in this container; probes until the first success."""
    with _state.lock:
        if _state.confirmed:
            return True
        failure = _run_probe()
        if failure is None:
            _state.confirmed = True
            _state.warned = False
            logger.info("NVENC probe succeeded; encoding video on the GPU")
            return True
        if not _state.warned:
            _state.warned = True
            logger.warning(
                "VIDEO_ENCODER=nvenc but NVENC is unusable in this container; encoding on the CPU "
                "(the probe is retried before the next video job). Check that the GPU compose override "
                "is applied and the driver exposes the `video` capability. %s",
                failure,
            )
        return False


def _run_probe() -> str | None:  # pragma: no cover - runs ffmpeg
    """Run the one-frame NVENC encode; return None on success, else the reason."""
    try:
        result = subprocess.run(nvenc_probe_command(), capture_output=True, timeout=_PROBE_TIMEOUT_SEC, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"The probe could not run: {e}"
    if result.returncode != 0:
        return "ffmpeg: " + result.stderr.decode("utf-8", errors="replace").strip()
    return None
