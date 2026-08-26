"""Shared test configuration."""

import logging
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `Settings` requires these two variables. Docker Compose injects them for the
# running app; default them here so `pytest` is self-contained on any host
# (Makefile, CI, IDE test runners). Nothing in the test suite creates OUTPUT_DIR.
os.environ.setdefault("RECORDING_CONFIG", str(REPO_ROOT / "config" / "simulator.yaml"))
os.environ.setdefault("OUTPUT_DIR", str(Path(tempfile.gettempdir()) / "open-lutra-test-output"))


@pytest.fixture(autouse=True)
def _restore_log_propagation() -> Iterator[None]:
    """Keep `caplog` working when tests run inside the ROS 2 image (Dev Container).

    With `/opt/ros/humble/setup.bash` sourced, pytest auto-loads ROS plugins.
    Loading them imports `launch.logging`, which calls
    `logging.setLoggerClass(LaunchLogger)`; every `LaunchLogger` sets
    `propagate = False` in its constructor. With propagation disabled, `app.*`
    log records never reach the root logger where pytest's `caplog` handler
    lives, so log-assertion tests see no records.

    Restore the standard logger class (so loggers created later propagate
    normally) and re-enable propagation on the `app.*` loggers that already
    exist from collection-time imports. On a plain host this is a no-op.
    """
    logging.setLoggerClass(logging.Logger)
    for name, candidate in logging.Logger.manager.loggerDict.items():
        if isinstance(candidate, logging.Logger) and (name == "app" or name.startswith("app.")):
            candidate.propagate = True
    yield
