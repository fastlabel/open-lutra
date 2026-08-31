"""Free-space inspection for the filesystem that holds a given path.

`statvfs` reports the filesystem a path lives on, so passing the output
directory (a bind-mounted host volume inside the container) yields the free
space of that volume rather than the container's own overlay filesystem. cgroup
has no notion of a disk-space limit, so there is no container-level counterpart
to `memory_reader.py` here.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def read_free_bytes(path: Path) -> int | None:
    """Return the bytes still writable on the filesystem containing `path`.

    Counts only the blocks available to an unprivileged process, so the blocks
    reserved for the superuser (5% by default on ext4) are excluded -- this is
    what the recorder can actually write, not the volume's nominal capacity.

    Returns None when the path cannot be inspected (e.g. it does not exist), so
    callers can degrade instead of failing. A hard-mounted network share that
    stops responding is not one of those cases: `statvfs` blocks in the kernel
    rather than raising, so there is nothing to degrade to and the call simply
    waits. Callers must therefore keep it off the event loop.
    """
    try:
        return shutil.disk_usage(path).free
    except OSError as e:
        logger.debug("Failed to read free space for %s: %s", path, e)
        return None
