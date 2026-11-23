"""Security and JSON-RPC protocol tests for `model-onboarding-mcp` (`mcp_app.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from model_onboarding.config import OnboardingSettings
from model_onboarding.controller import OnboardingController
from model_onboarding.mcp_app import create_onboarding_mcp_app
from model_onboarding.mcp_tools import OnboardingMcpDispatcher
from tests.test_pr_publisher_and_controller import _init_temp_git_repo, _StubSandboxWorker
from tests.test_sandbox_worker_and_sanitizer import _make_seed_xlsx


def test_mcp_app_security_headers_auth_rate_limit_and_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_temp_git_repo(tmp_path / "mcp_repo")
    seed = _make_seed_xlsx(tmp_path / "Grid_Dispatch_2026.xlsx")

    settings = OnboardingSettings(local_jobs_dir=tmp_path / "mcp_jobs")
    ctrl = OnboardingController(
        repo_root=repo,
        settings=settings,
        sandbox_worker=_StubSandboxWorker(),
    )
    dispatcher = OnboardingMcpDispatcher(controller=ctrl, settings=settings)
    app = create_onboarding_mcp_app(dispatcher=dispatcher, rate_limit_per_minute=10)

    # Bind strictly to localhost (127.0.0.1) in test client
    client = TestClient(app, base_url="http://127.0.0.1:8080")

    # 1. Healthz + security headers check
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in health.headers["Content-Security-Policy"]

    # 2. Disallowed HTTP method blocked (405)
    del_resp = client.delete("/mcp")
    assert del_resp.status_code == 405

    # 3. Bearer token enforcement when ONBOARD_API_BEARER_TOKEN is set
    monkeypatch.setenv("ONBOARD_API_BEARER_TOKEN", "test-ephemeral-token-123")
    unauth = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert unauth.status_code == 401

    auth_hdrs = {"Authorization": "Bearer test-ephemeral-token-123"}
    tools_resp = client.post(
        "/mcp",
        headers=auth_hdrs,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert tools_resp.status_code == 200
    tool_names = [t["name"] for t in tools_resp.json()["result"]["tools"]]
    assert "assess_workbook_onboarding_readiness" in tool_names
    assert "start_workbook_onboarding_job" in tool_names

    # 4. Stage 1 assessment via MCP
    assess_resp = client.post(
        "/mcp",
        headers=auth_hdrs,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "assess_workbook_onboarding_readiness",
                "arguments": {"workbook_uri": str(seed), "model_slug": "grid-dispatch"},
            },
        },
    )
    assert assess_resp.status_code == 200
    structured = assess_resp.json()["result"]["structuredContent"]
    assert structured["hygiene_report"]["decision"] in {"GO", "CONDITIONAL_GO"}
    assert "Exception Report" in structured["markdown_report"]

    # 5. Synchronous job submission + status lookup via MCP
    submit_resp = client.post(
        "/mcp",
        headers=auth_hdrs,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "start_workbook_onboarding_job",
                "arguments": {
                    "workbook_uri": str(seed),
                    "model_slug": "grid-dispatch",
                    "local_branch_only": True,
                    "run_sync": True,
                },
            },
        },
    )
    assert submit_resp.status_code == 200
    job_payload = submit_resp.json()["result"]["structuredContent"]
    assert job_payload["state"] == "AWAITING_PR_APPROVAL"

    status_resp = client.post(
        "/mcp",
        headers=auth_hdrs,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_onboarding_job_status",
                "arguments": {"job_id": job_payload["job_id"]},
            },
        },
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["result"]["structuredContent"]["pr_result"]["package_dir"] == "grid-dispatch-bq-twin"

    # 6. Rate limiter triggers 429 once 10 requests/minute exceeded
    hit_429 = False
    for _ in range(8):
        r = client.get("/healthz")
        if r.status_code == 429:
            hit_429 = True
            break
    assert hit_429 is True
