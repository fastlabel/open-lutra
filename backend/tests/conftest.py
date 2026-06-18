"""Shared test configuration."""

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _restore_log_propagation() -> Iterator[None]:
    """Keep `caplog` working under the ROS 2 environment.

    Tests run inside the ROS-enabled image with `/opt/ros/humble/setup.bash`
    sourced, which auto-loads ROS pytest plugins. Loading them imports
    `launch.logging`, which calls `logging.setLoggerClass(LaunchLogger)`; every
    `LaunchLogger` sets `propagate = False` in its constructor. With
    propagation disabled, `app.*` log records never reach the root logger where
    pytest's `caplog` handler lives, so log-assertion tests see no records.

    Restore the standard logger class (so loggers created later propagate
    normally) and re-enable propagation on the `app.*` loggers that already
    exist from collection-time imports.
    """
    logging.setLoggerClass(logging.Logger)
    for name, candidate in logging.Logger.manager.loggerDict.items():
        if isinstance(candidate, logging.Logger) and (name == "app" or name.startswith("app.")):
            candidate.propagate = True
    yield


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """rclpy-dependent tests that fail to import are auto-skipped (importorskip)."""
