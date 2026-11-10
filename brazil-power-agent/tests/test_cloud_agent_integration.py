"""Tests for Brazil Power v13 Cloud Run Remote MCP, A2A Agent Card/Handler, and Artifact Download Security."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(WORKSPACE_ROOT / "brazil-power-agent" / "src"), str(WORKSPACE_ROOT / "brazil-power-v13")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.api.main import create_app


def test_a2a_and_standalone_chat_routes_removed() -> None:
    """Verify standalone A2A and prompt-chat endpoints are removed while Remote MCP remains active."""
    client = TestClient(create_app())
    for removed_get in ("/.well-known/agent.json", "/.well-known/agent-card.json", "/a2a/app/.well-known/agent-card.json"):
        assert client.get(removed_get).status_code == 404
    assert client.post("/a2a/app", json={"jsonrpc": "2.0", "id": 1, "method": "message/send"}).status_code == 404
    assert client.post("/v1/agent/chat", json={"prompt": "test"}).status_code == 404


def test_remote_mcp_streamable_http_protocol() -> None:
    """Verify POST /mcp handles initialize, tools/list, and tools/call over Streamable HTTP."""
    client = TestClient(create_app())

    init_resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
    )
    assert init_resp.status_code == 200
    assert init_resp.json()["result"]["serverInfo"]["name"] == "brazil-power-mcp"

    list_resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert list_resp.status_code == 200
    tools = list_resp.json()["result"]["tools"]
    assert len(tools) == 7

    call_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_session_assumptions", "arguments": {"technologies": ["_01_CF", "_06_CF"]}},
        },
    )
    assert call_resp.status_code == 200
    result = call_resp.json()["result"]
    assert result["isError"] is False
    assert "General" in result["content"][0]["text"]


def test_rest_tool_invocation_and_download_security(tmp_path: Path, monkeypatch) -> None:
    """Verify /v1/agent/tools/{tool_name} and path-traversal / nosniff protections on download endpoints."""
    monkeypatch.setenv("BRAZIL_POWER_ARTIFACT_DIR", str(tmp_path))
    client = TestClient(create_app())

    tools_resp = client.get("/v1/agent/tools")
    assert tools_resp.status_code == 200
    assert len(tools_resp.json()["tools"]) == 7

    inv_resp = client.post(
        "/v1/agent/tools/get_session_assumptions",
        json={"session_id": "sec_test", "arguments": {"include_full_general_tab": True}},
    )
    assert inv_resp.status_code == 200
    assert inv_resp.json()["status"] == "ok"

    dl_resp = client.get("/v1/agent/artifacts/brazil_v13_general_assumptions.md")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in dl_resp.headers["content-disposition"]

    # Verify path traversal payloads are rejected with HTTP 400/404
    bad_art = client.get("/v1/agent/artifacts/..%2F..%2Fetc%2Fpasswd")
    assert bad_art.status_code in (400, 404)

    bad_exp = client.get("/v1/agent/exports/..%2Fsecret.xlsx")
    assert bad_exp.status_code in (400, 404)


def test_remote_mcp_sse_and_messages_queue() -> None:
    """Verify GET /mcp/sse?once=1 discovery and POST /mcp/messages queuing into _ACTIVE_SSE_QUEUES."""
    import asyncio
    import json
    from src.api.routes.agent_cloud import _ACTIVE_SSE_QUEUES

    client = TestClient(create_app())
    sse_resp = client.get("/mcp/sse?session_id=sse_test_1&once=1")
    assert sse_resp.status_code == 200
    assert "event: endpoint" in sse_resp.text
    assert "/mcp/messages?session_id=sse_test_1" in sse_resp.text

    # Simulate an active SSE queue for sse_test_2 and verify POST /mcp/messages pushes JSON-RPC frame
    q: asyncio.Queue[str | None] = asyncio.Queue()
    _ACTIVE_SSE_QUEUES["sse_test_2"] = q
    try:
        msg_resp = client.post(
            "/mcp/messages?session_id=sse_test_2",
            json={"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}},
        )
        assert msg_resp.status_code == 202
        queued_str = q.get_nowait()
        assert queued_str is not None
        queued_obj = json.loads(queued_str)
        assert queued_obj["id"] == 99
        assert len(queued_obj["result"]["tools"]) == 7
    finally:
        _ACTIVE_SSE_QUEUES.pop("sse_test_2", None)


def test_install_remote_sse_mcp_config(tmp_path: Path) -> None:
    """Verify install_skills_and_mcp(..., remote_sse=True) writes serverUrl without requiring local Python."""
    import json
    from brazil_power_agent.install_customizations import (
        DEFAULT_REMOTE_MCP_SSE_URL,
        install_skills_and_mcp,
    )

    status = install_skills_and_mcp(config_dir=tmp_path, remote_sse=True)
    assert status["all_valid"] is True
    assert status["mcp_registered"] is True
    mcp_cfg = json.loads((tmp_path / "mcp_config.json").read_text(encoding="utf-8"))
    assert mcp_cfg["mcpServers"]["brazil-power-mcp"] == {"serverUrl": DEFAULT_REMOTE_MCP_SSE_URL}

