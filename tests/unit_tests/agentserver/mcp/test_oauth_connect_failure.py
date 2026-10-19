"""OAuth finalization failures must produce a frontend response."""

from threading import RLock
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from jiuwenswarm.common import mcp_remote_oauth as oauth
from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
from jiuwenswarm.server.runtime.mcp import registry, state_store


@pytest.mark.asyncio
@pytest.mark.parametrize("grant_kind", ["corrupt", "empty", "same", "newer"])
async def test_finalize_failure_handles_corrupt_grant_and_preserves_newer_session(monkeypatch, grant_kind):
    manager = SimpleNamespace(
        lock=RLock(),
        finish=Mock(side_effect=oauth.OAuthError("cancelled")),
        grant=Mock(),
    )
    if grant_kind == "corrupt":
        manager.grant.side_effect = oauth.OAuthError("invalid grant")
    else:
        manager.grant.return_value = {} if grant_kind == "empty" else {
            "oauth_session": "new-session" if grant_kind == "newer" else "old-session"
        }
    monkeypatch.setattr(oauth, "oauth_manager", lambda: manager)
    monkeypatch.setattr(registry, "connect_mcp", lambda name: {})
    monkeypatch.setattr(registry, "was_connect_cancelled", lambda name: False)
    remove = Mock()
    monkeypatch.setattr(state_store, "remove_mcp_record", remove)
    server = SimpleNamespace(
        _agent_manager=SimpleNamespace(probe_mcp_live_connection=AsyncMock(return_value=(True, "")))
    )

    result = await AgentWebSocketServer._run_mcp_connect_flow(
        server, "qcc-company", oauth_session="old-session"
    )

    assert result["type"] == "connect_failed"
    assert result["code"] == "MCP_AUTH_FAILED"
    assert result["name"] == "qcc-company"
    if grant_kind == "newer":
        remove.assert_not_called()
    else:
        remove.assert_called_once_with("qcc-company")
