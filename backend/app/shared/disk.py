"""Capacity inspection for the filesystem that holds a given path.

`statvfs` reports the filesystem a path lives on, so passing the output
directory (a bind-mounted host volume inside the container) yields the capacity
of that volume rather than the container's own overlay filesystem. cgroup has no
notion of a disk-space limit, so there is no container-level counterpart to
`memory_reader.py` here.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiskUsage:
    """Capacity of a filesystem, in bytes.

    `total` counts every block including the ones reserved for the superuser
    (5% by default on ext4), while `free` counts only the blocks available to
    an unprivileged process. `used + free` is therefore smaller than `total` on
    such filesystems, so a "how full is it" ratio must be derived from a
    consistent pair rather than mixing the three.
    """

    total_bytes: int
    used_bytes: int
    free_bytes: int


def read_disk_usage(path: Path) -> DiskUsage | None:
    """Return the capacity of the filesystem containing `path`.

    Returns None when the path cannot be inspected (e.g. it does not exist, or
    an unresponsive network mount), so callers can degrade instead of failing.
    """
    try:
        usage = shutil.disk_usage(path)
    except OSError as e:
        logger.debug("Failed to read disk usage for %s: %s", path, e)
        return None
    return DiskUsage(total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free)
