"""Decide which encoder a process actually uses.

`VIDEO_ENCODER=nvenc` only expresses intent: the container may still lack a GPU
(started without the GPU compose override) or the driver may lack NVENC. A
one-frame probe, run once per process, settles it, so a misconfigured host
falls back to the CPU once instead of failing every encode first.
"""

import functools
import logging
import subprocess

from app.infra.video.commands import VideoEncoder, nvenc_probe_command

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SEC = 30


def resolve_encoder(requested: VideoEncoder, nvenc_usable: bool) -> VideoEncoder:
    """Return the encoder to use given the setting and whether NVENC passed its probe."""
    if requested == "nvenc" and not nvenc_usable:
        return "libx264"
    return requested


def effective_encoder(requested: VideoEncoder) -> VideoEncoder:  # pragma: no cover - runs ffmpeg
    """Resolve the configured encoder, probing NVENC (once per process) only when it is requested."""
    if requested == "nvenc":
        return resolve_encoder(requested, nvenc_usable())
    return requested


@functools.cache
def nvenc_usable() -> bool:  # pragma: no cover - runs ffmpeg
    """Probe NVENC once per process; logs a single warning when it is unusable."""
    try:
        result = subprocess.run(nvenc_probe_command(), capture_output=True, timeout=_PROBE_TIMEOUT_SEC, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("VIDEO_ENCODER=nvenc but the NVENC probe could not run (%s); encoding on the CPU", e)
        return False
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        logger.warning(
            "VIDEO_ENCODER=nvenc but NVENC is unusable in this container; encoding on the CPU. "
            "Check that the GPU compose override is applied and the driver exposes the `video` capability. "
            "ffmpeg: %s",
            stderr,
        )
        return False
    logger.info("NVENC probe succeeded; encoding video on the GPU")
    return True
