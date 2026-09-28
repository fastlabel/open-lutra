"""HTTP client for the external update agent.

The agent exposes `GET /status` -> {"available": bool, "applying": bool} and
`POST /apply`, which answers 409 when no update is pending.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request

from app.features.system_update.schemas import SystemUpdateStatus

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 3.0


class AgentUnavailableError(Exception):
    """The update agent could not be reached or answered unexpectedly."""


class NoPendingUpdateError(Exception):
    """The update agent has no update to apply."""


async def fetch_status(agent_url: str | None) -> SystemUpdateStatus:
    """Return the agent's update status; an unreachable agent reports no update."""
    if agent_url is None:
        return SystemUpdateStatus(enabled=False, available=False, applying=False)
    try:
        body = await asyncio.to_thread(_request, "GET", f"{agent_url}/status")
    except AgentUnavailableError as e:
        logger.warning("Update agent unavailable: %s", e)
        return SystemUpdateStatus(enabled=True, available=False, applying=False)
    return _to_status(body)


async def apply_update(agent_url: str | None) -> SystemUpdateStatus:
    """Ask the agent to apply the pending update.

    Raises:
        AgentUnavailableError: If no agent is configured or it cannot be reached.
        NoPendingUpdateError: If the agent has no pending update.
    """
    if agent_url is None:
        raise AgentUnavailableError("No update agent is configured")
    body = await asyncio.to_thread(_request, "POST", f"{agent_url}/apply")
    return _to_status(body)


def _request(method: str, url: str) -> dict[str, object]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            return json.loads(response.read())  # type: ignore[no-any-return]
    except urllib.error.HTTPError as e:
        if e.code == 409:
            raise NoPendingUpdateError from e
        raise AgentUnavailableError(f"{method} {url} returned {e.code}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise AgentUnavailableError(f"{method} {url} failed: {e}") from e


def _to_status(body: dict[str, object]) -> SystemUpdateStatus:
    return SystemUpdateStatus(
        enabled=True,
        available=bool(body.get("available")),
        applying=bool(body.get("applying")),
    )
