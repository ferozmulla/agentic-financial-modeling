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


def test_a2a_agent_card_endpoints() -> None:
    """Verify A2A agent card discovery endpoints expose the 5 Brazil Power v13 skills."""
    client = TestClient(create_app())
    for path in ("/.well-known/agent.json", "/.well-known/agent-card.json", "/a2a/app/.well-known/agent-card.json"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "brazil_power_v13_agent"
        assert data["url"].endswith("/a2a/app")
        skill_ids = {s["id"] for s in data["skills"]}
        assert {
            "brazil-power-model",
            "brazil-tornado",
            "brazil-bqml",
            "brazil-lcoe",
            "brazil-dcf",
        }.issubset(skill_ids)


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


def test_a2a_jsonrpc_task_execution() -> None:
    """Verify POST /a2a/app executes Tornado sensitivity when prompted via A2A message/send."""
    client = TestClient(create_app())
    resp = client.post(
        "/a2a/app",
        json={
            "jsonrpc": "2.0",
            "id": "a2a-test-1",
            "method": "message/send",
            "params": {
                "sessionId": "pytest_a2a_session",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Run Tornado IRR sensitivity for Natural Gas CCGT (_06_CF)"}],
                },
            },
        },
    )
    assert resp.status_code == 200
    payload = resp.json()["result"]
    assert payload["status"]["state"] == "completed"
    assert "run_tornado_sensitivity" in payload["metadata"]["executed_tools"]
    assert "_06_CF" in payload["status"]["message"]["parts"][0]["text"]


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
