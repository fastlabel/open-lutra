"""Tests for the update agent HTTP client."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.features.system_update.agent_client import (
    AgentUnavailableError,
    NoPendingUpdateError,
    apply_update,
    fetch_status,
)
from app.features.system_update.schemas import SystemUpdateStatus


class _Agent:
    """A local HTTP server standing in for the update agent."""

    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], tuple[int, bytes]] = {}
        agent = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._reply("GET")

            def do_POST(self) -> None:
                self._reply("POST")

            def log_message(self, format: str, *args: object) -> None:
                pass

            def _reply(self, method: str) -> None:
                code, body = agent.responses.get((method, self.path), (404, b"{}"))
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def agent() -> Iterator[_Agent]:
    agent = _Agent()
    thread = threading.Thread(target=agent.server.serve_forever, daemon=True)
    thread.start()
    yield agent
    agent.server.shutdown()
    agent.server.server_close()


class TestFetchStatus:
    async def test_disabled_without_agent(self) -> None:
        assert await fetch_status(None) == SystemUpdateStatus(enabled=False, available=False, applying=False)

    async def test_reports_agent_status(self, agent: _Agent) -> None:
        agent.responses["GET", "/status"] = (200, b'{"available": true, "applying": false}')
        assert await fetch_status(agent.url) == SystemUpdateStatus(enabled=True, available=True, applying=False)

    async def test_unreachable_agent_reports_no_update(self) -> None:
        status = await fetch_status("http://127.0.0.1:9")
        assert status == SystemUpdateStatus(enabled=True, available=False, applying=False)

    async def test_error_response_reports_no_update(self, agent: _Agent) -> None:
        agent.responses["GET", "/status"] = (500, b"{}")
        assert (await fetch_status(agent.url)).available is False

    async def test_invalid_json_reports_no_update(self, agent: _Agent) -> None:
        agent.responses["GET", "/status"] = (200, b"not json")
        assert (await fetch_status(agent.url)).available is False


class TestApplyUpdate:
    async def test_applies_pending_update(self, agent: _Agent) -> None:
        agent.responses["POST", "/apply"] = (202, b'{"available": true, "applying": true}')
        assert await apply_update(agent.url) == SystemUpdateStatus(enabled=True, available=True, applying=True)

    async def test_no_pending_update(self, agent: _Agent) -> None:
        agent.responses["POST", "/apply"] = (409, b'{"detail": "no pending update"}')
        with pytest.raises(NoPendingUpdateError):
            await apply_update(agent.url)

    async def test_without_agent(self) -> None:
        with pytest.raises(AgentUnavailableError):
            await apply_update(None)

    async def test_unreachable_agent(self) -> None:
        with pytest.raises(AgentUnavailableError):
            await apply_update("http://127.0.0.1:9")
