from __future__ import annotations

import io
import json
from pathlib import Path

from brazil_power_agent.mcp_server import (
    MCP_TOOLS,
    build_mcp_server_config_entry,
    handle_jsonrpc_request,
    serve_stdio_stream,
)
from brazil_power_agent.session_store import BrazilPowerSessionManager


def test_mcp_jsonrpc_tools_list_and_call(tmp_path: Path) -> None:
    session_file = tmp_path / "mcp_session.json"
    mgr = BrazilPowerSessionManager(session_path=session_file)

    init_resp = handle_jsonrpc_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        session_mgr=mgr,
    )
    assert init_resp is not None
    assert "protocolVersion" in init_resp["result"]
    assert init_resp["result"]["serverInfo"]["name"] == "brazil-power-mcp"

    notif_resp = handle_jsonrpc_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        session_mgr=mgr,
    )
    assert notif_resp is None

    ping_resp = handle_jsonrpc_request(
        {"jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}},
        session_mgr=mgr,
    )
    assert ping_resp == {"jsonrpc": "2.0", "id": 99, "result": {}}

    list_resp = handle_jsonrpc_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        session_mgr=mgr,
    )
    assert list_resp is not None
    tools = list_resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    assert tool_names == {
        "get_session_assumptions",
        "update_session_assumptions",
        "run_tornado_sensitivity",
        "run_bqml_timeseries_refresh",
        "run_lcoe_horizon_forecast",
        "run_dcf_cashflow_analysis",
        "export_full_22tab_workbook",
    }
    assert len(MCP_TOOLS) == 7
    for tool_def in tools:
        assert "inputSchema" in tool_def
        assert tool_def["inputSchema"]["type"] == "object"

    call_resp = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "run_tornado_sensitivity",
                "arguments": {"technology_code": "_06_CF"},
            },
        },
        session_mgr=mgr,
    )
    assert call_resp is not None
    assert not call_resp["result"].get("isError", False)
    text_out = call_resp["result"]["content"][0]["text"]
    assert "_06_CF" in text_out


def test_all_7_mcp_tools_return_markdown_echarts_and_structured_json(tmp_path: Path) -> None:
    session_file = tmp_path / "all_tools_session.json"
    mgr = BrazilPowerSessionManager(session_path=session_file)

    # 1. get_session_assumptions
    r1 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "get_session_assumptions",
                "arguments": {"technologies": ["_01_CF", "_06_CF"], "include_full_general_tab": True},
            },
        },
        session_mgr=mgr,
    )
    assert r1 is not None and not r1["result"].get("isError", False)
    p1 = json.loads(r1["result"]["content"][-1]["text"])
    assert "General!B5:N40" in p1["inline_markdown"]
    assert "Full 12-Technology Excel Tab Replica" in p1["artifact_markdown"]

    # 2. update_session_assumptions
    r2 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "update_session_assumptions",
                "arguments": {
                    "overrides": {
                        "_01_CF": {"fuel_cost_r_per_mmbtu": 6.50, "real_wacc": 0.09},
                        "_06_CF": {"lead_time_years": 2.0},
                    },
                    "reset_to_baseline": False,
                },
            },
        },
        session_mgr=mgr,
    )
    assert r2 is not None and not r2["result"].get("isError", False)
    p2 = json.loads(r2["result"]["content"][-1]["text"])
    assert p2["modified_count"] == 3
    assert "General!C20" in p2["inline_markdown"]
    assert "General!H14" in p2["inline_markdown"]
    assert "Full 12-Technology Excel Tab Replica" in p2["artifact_markdown"]

    # 3. run_tornado_sensitivity
    r3 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "run_tornado_sensitivity",
                "arguments": {"technology_code": "_06_CF"},
            },
        },
        session_mgr=mgr,
    )
    assert r3 is not None and not r3["result"].get("isError", False)
    p3 = json.loads(r3["result"]["content"][-1]["text"])
    assert "_06_CF!A4:H12" in p3["inline_markdown"]
    assert "_06_CF!A4:H12" in p3["artifact_markdown"]
    assert "series" in p3["echarts_option"]

    # 4. run_bqml_timeseries_refresh
    r4 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "run_bqml_timeseries_refresh",
                "arguments": {"curve_types": ["CAPEX", "FUEL", "CF"], "apply_to_session_lt_tabs": True},
            },
        },
        session_mgr=mgr,
    )
    assert r4 is not None and not r4["result"].get("isError", False)
    p4 = json.loads(r4["result"]["content"][-1]["text"])
    assert "LT Capex!B8:J30" in p4["inline_markdown"]
    assert "LT Fuel!B8:J30" in p4["artifact_markdown"]
    assert "series" in p4["echarts_option"]

    # 5. run_lcoe_horizon_forecast
    r5 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {
                "name": "run_lcoe_horizon_forecast",
                "arguments": {"parity_mode": "strict_legacy_vba"},
            },
        },
        session_mgr=mgr,
    )
    assert r5 is not None and not r5["result"].get("isError", False)
    p5 = json.loads(r5["result"]["content"][-1]["text"])
    assert "Output_3!B9:J31" in p5["inline_markdown"]
    assert "2046" in p5["artifact_markdown"]
    assert "series" in p5["echarts_option"]

    # 6. run_dcf_cashflow_analysis (with include_cvu_gf_sweep=True)
    r6 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {
                "name": "run_dcf_cashflow_analysis",
                "arguments": {
                    "technology_code": "_07_CF",
                    "start_year": 2024,
                    "end_year": 2053,
                    "include_cvu_gf_sweep": True,
                },
            },
        },
        session_mgr=mgr,
    )
    assert r6 is not None and not r6["result"].get("isError", False)
    p6 = json.loads(r6["result"]["content"][-1]["text"])
    assert "_07_CF" in p6["inline_markdown"]
    assert "2053" in p6["artifact_markdown"]
    assert "series" in p6["echarts_option"]
    assert "cvu_gf_sweep" in p6
    assert "calculo_cvu7" in p6["cvu_gf_sweep"]["macro_name"]
    assert "CVU_GF" in p6["inline_markdown"]

    # 7. export_full_22tab_workbook
    r7 = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {
                "name": "export_full_22tab_workbook",
                "arguments": {
                    "export_format": "xlsx",
                    "output_dir": str(tmp_path),
                    "output_filename": "mcp_exported_22tab.xlsx",
                },
            },
        },
        session_mgr=mgr,
    )
    assert r7 is not None and not r7["result"].get("isError", False)
    p7 = json.loads(r7["result"]["content"][-1]["text"])
    assert p7["tabs_preserved"] == 22
    assert Path(p7["xlsx_path"]).exists()
    assert "Full 22-Tab Brazil Power Workbook Export" in p7["inline_markdown"]


def test_stdio_framing_newline_and_content_length(tmp_path: Path) -> None:
    mgr = BrazilPowerSessionManager(session_path=tmp_path / "stdio_session.json")

    # 1. Test newline-delimited JSON-RPC 2.0
    req_line = json.dumps({"jsonrpc": "2.0", "id": 101, "method": "ping", "params": {}}) + "\n"
    in_buf = io.BytesIO(req_line.encode("utf-8"))
    out_buf = io.BytesIO()
    serve_stdio_stream(in_buf, out_buf, session_mgr=mgr)
    out_text = out_buf.getvalue().decode("utf-8").strip()
    parsed_newline = json.loads(out_text)
    assert parsed_newline["id"] == 101
    assert parsed_newline["result"] == {}

    # 2. Test Content-Length framed JSON-RPC 2.0
    body_bytes = json.dumps({"jsonrpc": "2.0", "id": 202, "method": "tools/list", "params": {}}).encode("utf-8")
    framed_msg = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("ascii") + body_bytes
    in_framed = io.BytesIO(framed_msg)
    out_framed = io.BytesIO()
    serve_stdio_stream(in_framed, out_framed, session_mgr=mgr)
    raw_framed_out = out_framed.getvalue()
    assert raw_framed_out.startswith(b"Content-Length:")
    _, payload_bytes = raw_framed_out.split(b"\r\n\r\n", 1)
    parsed_framed = json.loads(payload_bytes.decode("utf-8"))
    assert parsed_framed["id"] == 202
    assert len(parsed_framed["result"]["tools"]) == 7


def test_mcp_config_helper(tmp_path: Path) -> None:
    cfg_entry = build_mcp_server_config_entry(tmp_path)
    assert "command" in cfg_entry
    assert "args" in cfg_entry
    assert "PYTHONPATH" in cfg_entry["env"]


def test_compact_llm_payload_and_presaved_artifacts(tmp_path: Path) -> None:
    session_file = tmp_path / "compact_session.json"
    mgr = BrazilPowerSessionManager(session_path=session_file)

    resp = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 301,
            "method": "tools/call",
            "params": {
                "name": "run_dcf_cashflow_analysis",
                "arguments": {
                    "technology_code": "_06_CF",
                    "start_year": 2024,
                    "end_year": 2053,
                    "include_cvu_gf_sweep": True,
                },
            },
        },
        session_mgr=mgr,
    )
    assert resp is not None and not resp["result"].get("isError", False)

    compact_text = resp["result"]["content"][-1]["text"]
    compact_payload = json.loads(compact_text)
    full_structured = resp["result"]["structuredContent"]
    full_text = json.dumps(full_structured)

    # Cause 3: Artifact markdown is pre-saved directly to disk in < 1 ms
    assert "artifact_file_path" in compact_payload
    assert "artifact_file_uri" in compact_payload
    assert compact_payload["artifact_file_uri"].startswith("file://")
    saved_artifact = Path(compact_payload["artifact_file_path"])
    assert saved_artifact.is_file()
    assert "_06_CF" in saved_artifact.read_text(encoding="utf-8")

    # Cause 3: Compact LLM payload strips duplicate keys & bulky raw arrays from content[-1]["text"]
    assert "inline_excel_table_md" not in compact_payload
    assert "full_artifact_table_md" not in compact_payload
    assert "echarts_spec" not in compact_payload
    assert "inline_excel_table_md" in full_structured
    assert "full_artifact_table_md" in full_structured
    assert "echarts_spec" in full_structured
    assert len(compact_text) < len(full_text) * 0.55

    # Verify General!B5:N40 artifact table is multi-line, has zero '$' LaTeX collisions, and repairs '| |'
    from brazil_power_agent.excel_renderer import normalize_markdown_table

    gen_resp = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 302,
            "method": "tools/call",
            "params": {
                "name": "update_session_assumptions",
                "arguments": {
                    "overrides": {
                        "_01_CF": {"fuel_cost_r_per_mmbtu": 6.50},
                        "_06_CF": {"lead_time_years": 2.0},
                    }
                },
            },
        },
        session_mgr=mgr,
    )
    assert gen_resp is not None and not gen_resp["result"].get("isError", False)
    gen_payload = json.loads(gen_resp["result"]["content"][-1]["text"])
    gen_artifact_text = Path(gen_payload["artifact_file_path"]).read_text(encoding="utf-8")
    assert "$" not in gen_artifact_text
    assert "| |" not in gen_artifact_text
    table_lines = [ln for ln in gen_artifact_text.splitlines() if ln.startswith("|")]
    assert len(table_lines) >= 34
    expected_pipes = table_lines[0].count("|")
    assert expected_pipes == 16  # 15 columns (Row, Parameter, Unit, Col C..Col N)
    for tline in table_lines:
        assert tline.count("|") == expected_pipes

    # Verify collapsed single-line '| |' table is repaired into multi-line rows
    collapsed = "# Title\n\n| Col A | Col B | | --- | --- | | 1 | R$/kW |"
    repaired = normalize_markdown_table(collapsed)
    assert "$" not in repaired
    assert len([ln for ln in repaired.splitlines() if ln.startswith("|")]) == 3

    # Verify content[0]["text"] (and CLI --call default output) is real multi-line Markdown with physical newlines
    multiline_report_text = gen_resp["result"]["content"][0]["text"]
    assert "### Full Multi-Line Artifact Markdown Replica" in multiline_report_text
    assert "| |" not in multiline_report_text
    report_table_lines = [ln for ln in multiline_report_text.splitlines() if ln.startswith("|")]
    assert len(report_table_lines) >= 36


