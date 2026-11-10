"""Tests for the FastAPI Remote SSE/HTTP MCP server, security headers, and isolated Cowork skills."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from brazil_power_bq_twin.bq_store import InMemoryDigitalTwinStore
from brazil_power_bq_twin.config import TwinSettings
from brazil_power_bq_twin.mcp_app import _ACTIVE_SSE_QUEUES, create_twin_mcp_app
from brazil_power_bq_twin.xlsm_compiler import compile_workbook_to_twin_payload

from test_xlsm_compiler import _create_synthetic_22tab_workbook

TWIN_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TWIN_SKILLS = (
    "brazil-power-model-gcp",
    "brazil-tornado-gcp",
    "brazil-bqml-gcp",
    "brazil-lcoe-gcp",
    "brazil-dcf-gcp",
)


def test_mcp_http_sse_and_download_security(tmp_path: Path) -> None:
    wb_path = _create_synthetic_22tab_workbook(tmp_path / "seed_once.xlsx")
    snap = compile_workbook_to_twin_payload(wb_path).snapshot
    wb_path.unlink()

    lt_mock = {
        "data_source": "bigquery_ml_digital_twin",
        "years": list(range(2024, 2047)),
        "curves": {
            "CAPEX": [[1.0] * 9 for _ in range(23)],
            "FUEL": [[1.02] * 9 for _ in range(23)],
            "CF": [[0.48] * 9 for _ in range(23)],
        },
    }
    store = InMemoryDigitalTwinStore(snap, lt_trajectories=lt_mock)
    settings = TwinSettings(
        local_export_dir=tmp_path / "exports",
        local_artifact_dir=tmp_path / "artifacts",
    )
    app = create_twin_mcp_app(store=store, settings=settings)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["excel_files_used"] == 0
    assert health.json()["backend"] == "bigquery_digital_twin"

    # Streamable HTTP MCP
    init_r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_r.status_code == 200
    assert init_r.json()["result"]["serverInfo"]["name"] == "brazil-power-bq-twin-mcp"

    list_r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert len(list_r.json()["result"]["tools"]) == 7

    # Call Tornado & Export via MCP
    call_r = client.post(
        "/mcp?session_id=mcp_s1",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "run_tornado_sensitivity", "arguments": {"technology_code": "_01_CF"}},
        },
    )
    assert call_r.status_code == 200
    assert call_r.json()["result"]["isError"] is False
    assert "BigQuery Digital Twin" in call_r.json()["result"]["content"][0]["text"]

    exp_r = client.post(
        "/mcp?session_id=mcp_s1",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "export_full_22tab_workbook",
                "arguments": {"export_format": "xlsx", "output_filename": "Synthesized_Test.xlsx"},
            },
        },
    )
    assert exp_r.status_code == 200
    assert exp_r.json()["result"]["isError"] is False

    dl_xlsx = client.get("/v1/exports/Synthesized_Test.xlsx")
    assert dl_xlsx.status_code == 200
    assert dl_xlsx.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in dl_xlsx.headers["content-disposition"]

    # Path traversal blocked
    bad = client.get("/v1/exports/..%2F..%2Fetc%2Fpasswd")
    assert bad.status_code in (400, 404)

    # Full-duplex SSE queue check
    sse_r = client.get("/mcp/sse?session_id=sse_1&once=1")
    assert sse_r.status_code == 200
    assert "event: endpoint" in sse_r.text

    q: asyncio.Queue[str | None] = asyncio.Queue()
    _ACTIVE_SSE_QUEUES["sse_2"] = q
    try:
        m_resp = client.post(
            "/mcp/messages?session_id=sse_2",
            json={"jsonrpc": "2.0", "id": 77, "method": "tools/list", "params": {}},
        )
        assert m_resp.status_code == 202
        msg = json.loads(q.get_nowait() or "{}")
        assert msg["id"] == 77
        assert len(msg["result"]["tools"]) == 7
    finally:
        _ACTIVE_SSE_QUEUES.pop("sse_2", None)


def test_five_isolated_bq_twin_skills_present_and_valid() -> None:
    for skill_id in EXPECTED_TWIN_SKILLS:
        s_path = TWIN_ROOT / "skills" / skill_id / "SKILL.md"
        assert s_path.is_file(), f"Missing skill file: {s_path}"
        text = s_path.read_text(encoding="utf-8")
        assert f"name: {skill_id}" in text
        assert "brazil-power-bq-twin-mcp" in text
        assert "ask_question" in text
        assert "write_to_file" in text
