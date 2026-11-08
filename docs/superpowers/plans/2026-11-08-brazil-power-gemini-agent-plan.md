# Brazil Energy Model (v13) — Native Gemini App Skills & MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent prototype (`brazil-power-agent/`) that encapsulates the 22-tab Brazil Power Generation Techno-Economic Model (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`) inside the Gemini App via 5 `/` skills, a 7-tool MCP server (`brazil-power-mcp`), native interactive cards (`ask_question`), inline Excel-layout tables + Apache ECharts visuals (`render_chart`), side-pane multi-column Excel-tab Artifacts, and full 22-tab `.xlsx` / Google Sheets export.

**Architecture:** An independent Python package under `brazil-power-agent/` reuses the vectorized Brazil Power quantitative solver (`MacroExecutionRegistry`, `VectorizedCashFlowEngine`, and `SeedWorkbookLoader`) in read-only fashion from `brazil-power-v13/src/`, manages per-session scenario overrides in `~/.gemini/jetski/brazil_power_agent_session.json`, formats outputs as exact Excel-coordinate Markdown tables and ECharts V5 specs, clones all 22 tabs of the original `.xlsm` / Golden Google Sheet on export, exposes an MCP server registered in `~/.gemini/config/mcp_config.json`, provides an ADK agent wrapper targeting the GCP Gemini Enterprise App (`comm-model-mod`, location `us`, `cid/cb0f4566-dfad-496c-9b28-3542d86a5367`), and installs 5 skills (`/brazil-power-model`, `/brazil-tornado`, `/brazil-lcoe`, `/brazil-bqml`, `/brazil-dcf`) in `~/.gemini/config/skills/`.

**Tech Stack:** Python 3.11, NumPy/SciPy, `openpyxl`, Google BigQuery / Drive / Sheets Python clients, JSON-RPC 2.0 MCP Stdio Server, Google ADK (`google-adk`), Apache ECharts V5 (`render_chart`), Gemini App Skills (`SKILL.md`).

## Global Constraints

- **No Custom Web UI**: All interaction happens inside the Gemini App (`Chat App`) via `/skills`, `ask_question` visual cards, `render_chart` visuals, inline Markdown tables, and side-pane Artifacts.
- **Complete Isolation from v1 Dashboards**: Do not modify or write events to the existing `brazil-power-v13` `/telemetry` or `/governance` dashboards.
- **Exact Excel Layout Fidelity**: In-app tables must include the original Excel tab names, row numbers, column letters (`Col C` .. `Col N`), parameter names, and units from `2023-11-27-Brazil_TT_v13_RJEB.xlsm`.
- **Full 22-Tab Workbook Export**: Any `.xlsx` or Google Sheets export must contain all 22 original tabs (`Version Control`, `General`, `Output_1`, `Output_2`, `Output_3`, `_01_CF` .. `_12_CF`, `_CAPEX 01`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`) preserving original styles, formulas, and layout.
- **GCP Gemini Enterprise Reference**: Project `comm-model-mod`, location `us`, Config ID `cb0f4566-dfad-496c-9b28-3542d86a5367` (`https://vertexaisearch.cloud.google.com/us/home/cid/cb0f4566-dfad-496c-9b28-3542d86a5367?hl=en_US`).

---

### Task 1: Stateful Session Manager & Excel-Layout Table / ECharts Renderer

**Files:**
- Create: `brazil-power-agent/src/__init__.py`
- Create: `brazil-power-agent/src/session_store.py`
- Create: `brazil-power-agent/src/excel_renderer.py`
- Test: `brazil-power-agent/tests/test_session_and_renderer.py`

**Interfaces:**
- Consumes: `SeedWorkbookLoader`, `MacroExecutionRegistry`, `VectorizedCashFlowEngine` from `brazil-power-v13/src/`
- Produces:
  - `BrazilPowerSessionManager(session_path: Path | None = None)` with methods:
    - `get_assumptions(technologies: list[str] | None = None) -> dict[str, Any]`
    - `update_assumptions(overrides: dict[str, dict[str, float]] | dict[str, float], reset_to_baseline: bool = False) -> dict[str, Any]`
    - `run_tornado(technology_code: str = "_06_CF") -> dict[str, Any]`
    - `run_lcoe_horizon(parity_mode: str = "strict_legacy_vba") -> dict[str, Any]`
    - `run_bqml_refresh(curve_types: list[str] | None = None) -> dict[str, Any]`
    - `run_dcf(technology_code: str = "_01_CF") -> dict[str, Any]`

- [ ] **Step 1: Write the failing test in `brazil-power-agent/tests/test_session_and_renderer.py`**

```python
from pathlib import Path
from brazil_power_agent.session_store import BrazilPowerSessionManager


def test_session_assumptions_and_analysis_rendering(tmp_path: Path) -> None:
    mgr = BrazilPowerSessionManager(session_path=tmp_path / "session.json")
    base = mgr.get_assumptions(technologies=["_01_CF", "_06_CF"])
    assert "General!C20" in base["inline_excel_table_md"] or "Fuel" in base["inline_excel_table_md"]
    assert "Col C" in base["full_artifact_table_md"]

    upd = mgr.update_assumptions(
        overrides={"General!C20": 6.50, "General!H14": 2.0},
        reset_to_baseline=False,
    )
    assert upd["modified_count"] == 2
    assert "6.50" in upd["diff_table_md"]

    tornado = mgr.run_tornado(technology_code="_06_CF")
    assert "_06_CF" in tornado["inline_excel_table_md"]
    assert "series" in tornado["echarts_spec"]

    lcoe = mgr.run_lcoe_horizon()
    assert "Output_3" in lcoe["inline_excel_table_md"]
    assert "2024" in lcoe["full_artifact_table_md"]
    assert "2046" in lcoe["full_artifact_table_md"]

    dcf = mgr.run_dcf(technology_code="_01_CF")
    assert "_01_CF" in dcf["inline_summary_table_md"]
    assert "2053" in dcf["full_artifact_table_md"]
    assert "series" in dcf["echarts_spec"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_session_and_renderer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_agent'`

- [ ] **Step 3: Implement `brazil-power-agent/src/brazil_power_agent/session_store.py` and `excel_renderer.py`**

Implement `BrazilPowerSessionManager` and `ExcelLayoutRenderer` reading the 22-tab seed workbook (`brazil-power-v13/seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm`), staging `General` and `LT` cell overrides in JSON, running `MacroExecutionRegistry` and `VectorizedCashFlowEngine`, and generating exact Excel-coordinate Markdown tables and Apache ECharts V5 specs.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_session_and_renderer.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-agent/src/ brazil-power-agent/tests/test_session_and_renderer.py
git commit -m "feat(brazil-power-agent): add stateful session store and Excel-layout table/ECharts renderer"
```

---

### Task 2: Full 22-Tab Excel (`.xlsx`) & Google Sheets Workbook Cloner

**Files:**
- Create: `brazil-power-agent/src/brazil_power_agent/workbook_exporter.py`
- Test: `brazil-power-agent/tests/test_workbook_exporter.py`

**Interfaces:**
- Consumes: `BrazilPowerSessionManager` session state and `brazil-power-v13/seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm`
- Produces:
  - `export_full_22tab_workbook(session_mgr: BrazilPowerSessionManager, export_format: str = "xlsx", output_dir: Path | None = None, filename: str | None = None, sheet_title: str | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test in `brazil-power-agent/tests/test_workbook_exporter.py`**

```python
from pathlib import Path
import openpyxl
from brazil_power_agent.session_store import BrazilPowerSessionManager
from brazil_power_agent.workbook_exporter import export_full_22tab_workbook


def test_export_22tab_xlsx_preserves_all_sheets_and_applies_session_edits(tmp_path: Path) -> None:
    mgr = BrazilPowerSessionManager(session_path=tmp_path / "session.json")
    mgr.update_assumptions(overrides={"General!C20": 6.50, "General!H14": 2.0})
    mgr.run_tornado(technology_code="_06_CF")
    mgr.run_lcoe_horizon()

    res = export_full_22tab_workbook(
        session_mgr=mgr,
        export_format="xlsx",
        output_dir=tmp_path,
        filename="Brazil_TT_v13_Scenario_Test.xlsx",
    )
    xlsx_path = Path(res["xlsx_path"])
    assert xlsx_path.exists()

    wb = openpyxl.load_workbook(xlsx_path, data_only=False)
    assert len(wb.sheetnames) == 22
    assert wb["General"]["C20"].value == 6.50
    assert wb["General"]["H14"].value == 2.0
    assert wb["Output_3"]["B9"].value is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_workbook_exporter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_agent.workbook_exporter'`

- [ ] **Step 3: Implement `brazil-power-agent/src/brazil_power_agent/workbook_exporter.py`**

Load `brazil-power-v13/seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm` via `openpyxl.load_workbook(..., keep_vba=False)` so all 22 tabs, cell styles, number formats, borders, column widths, and Excel formulas remain intact; write all session input cell overrides and solved macro output grids (`_01_CF.._12_CF!E6:G12`, `Output_3!B9:J31`, `Output_3!B3`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`); save as `.xlsx`; and support optional Drive copy + `spreadsheets.values.batchUpdate` for `"google_sheets"` format.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_workbook_exporter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-agent/src/brazil_power_agent/workbook_exporter.py brazil-power-agent/tests/test_workbook_exporter.py
git commit -m "feat(brazil-power-agent): add 22-tab faithful Excel and Google Sheets workbook cloner"
```

---

### Task 3: MCP Stdio Server (`brazil-power-mcp`), ADK Agent Wrapper & `~/.gemini/config/mcp_config.json` Registration

**Files:**
- Create: `brazil-power-agent/src/brazil_power_agent/mcp_server.py`
- Create: `brazil-power-agent/src/brazil_power_agent/adk_agent/agent.py`
- Test: `brazil-power-agent/tests/test_mcp_server.py`
- Modify: `~/.gemini/config/mcp_config.json`

**Interfaces:**
- Consumes: `BrazilPowerSessionManager`, `export_full_22tab_workbook`
- Produces: 7 MCP tools (`get_session_assumptions`, `update_session_assumptions`, `run_tornado_sensitivity`, `run_bqml_timeseries_refresh`, `run_lcoe_horizon_forecast`, `run_dcf_cashflow_analysis`, `export_full_22tab_workbook`) over JSON-RPC 2.0 Stdio + ADK `root_agent`.

- [ ] **Step 1: Write the failing test in `brazil-power-agent/tests/test_mcp_server.py`**

```python
from brazil_power_agent.mcp_server import handle_jsonrpc_request


def test_mcp_jsonrpc_tools_list_and_call() -> None:
    init_resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert "protocolVersion" in init_resp["result"]

    list_resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_names = {t["name"] for t in list_resp["result"]["tools"]}
    assert tool_names == {
        "get_session_assumptions",
        "update_session_assumptions",
        "run_tornado_sensitivity",
        "run_bqml_timeseries_refresh",
        "run_lcoe_horizon_forecast",
        "run_dcf_cashflow_analysis",
        "export_full_22tab_workbook",
    }

    call_resp = handle_jsonrpc_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "run_tornado_sensitivity",
            "arguments": {"technology_code": "_06_CF"},
        },
    })
    assert not call_resp["result"].get("isError", False)
    text_out = call_resp["result"]["content"][0]["text"]
    assert "_06_CF" in text_out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_mcp_server.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_agent.mcp_server'`

- [ ] **Step 3: Implement `mcp_server.py`, `adk_agent/agent.py`, and register `brazil-power-mcp` in `~/.gemini/config/mcp_config.json`**

Implement the zero-dependency JSON-RPC 2.0 Stdio MCP server (`mcp_server.py`) plus the ADK `root_agent` (`adk_agent/agent.py` configured with the same 7 tools and referencing GCP Gemini Enterprise App `cb0f4566-dfad-496c-9b28-3542d86a5367`), and merge `brazil-power-mcp` into `~/.gemini/config/mcp_config.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_mcp_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-agent/src/brazil_power_agent/mcp_server.py brazil-power-agent/src/brazil_power_agent/adk_agent/ brazil-power-agent/tests/test_mcp_server.py
git commit -m "feat(brazil-power-agent): add 7-tool MCP stdio server and ADK agent wrapper"
```

---

### Task 4: Gemini App `/skills` Suite (`brazil-power-model`, `brazil-tornado`, `brazil-lcoe`, `brazil-bqml`, `brazil-dcf`)

**Files:**
- Create: `brazil-power-agent/skills/brazil-power-model/SKILL.md`
- Create: `brazil-power-agent/skills/brazil-tornado/SKILL.md`
- Create: `brazil-power-agent/skills/brazil-lcoe/SKILL.md`
- Create: `brazil-power-agent/skills/brazil-bqml/SKILL.md`
- Create: `brazil-power-agent/skills/brazil-dcf/SKILL.md`
- Create: `brazil-power-agent/scripts/install_gemini_customizations.py`
- Test: `brazil-power-agent/tests/test_skills_installation.py`

**Interfaces:**
- Consumes: `brazil-power-mcp` tools, Gemini App native `ask_question` tool, `data-agent-kit:render_chart` tool, and `write_to_file` Artifact tool.
- Produces: 5 validated skills installed in `~/.gemini/config/skills/` and versioned in `brazil-power-agent/skills/`.

- [ ] **Step 1: Write the failing test in `brazil-power-agent/tests/test_skills_installation.py`**

```python
from pathlib import Path
from brazil_power_agent.install_customizations import verify_skills_and_mcp_installed


def test_all_five_skills_and_mcp_registered() -> None:
    status = verify_skills_and_mcp_installed()
    assert status["mcp_registered"] is True
    assert set(status["installed_skills"]) == {
        "brazil-power-model",
        "brazil-tornado",
        "brazil-lcoe",
        "brazil-bqml",
        "brazil-dcf",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/test_skills_installation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_agent.install_customizations'`

- [ ] **Step 3: Author the 5 `SKILL.md` files and `install_customizations.py` and install them into `~/.gemini/config/`**

Author the 5 `SKILL.md` workflow runbooks instructing the Gemini App agent how to:
1. Present native interactive visual cards (`ask_question`) for assumption inputs (with current baseline values displayed) and analysis selection (`Tornado`, `BQML Forecast`, `23-Yr LCOE`, `30-Yr DCF`, `CVU Sweep`).
2. Call `brazil-power-mcp` tools (`get_session_assumptions`, `update_session_assumptions`, `run_tornado_sensitivity`, `run_bqml_timeseries_refresh`, `run_lcoe_horizon_forecast`, `run_dcf_cashflow_analysis`, `export_full_22tab_workbook`).
3. Render the exact Excel-layout Markdown tables and inline ECharts visuals (`render_chart`) in the chat response AND write full multi-column Excel-tab replicas (`General!B5:N40`, `Output_3!B8:J31`, `_01_CF.._12_CF` 30-year DCF schedule) to a side-pane Artifact.
4. Offer 1-click full 22-tab `.xlsx` or Google Sheets export.

- [ ] **Step 4: Run full test suite to verify all tests pass**

Run: `PYTHONPATH=brazil-power-agent/src:brazil-power-v13 pytest brazil-power-agent/tests/ -q`
Expected: PASS (4 test files, all green)

- [ ] **Step 5: Commit**

```bash
git add brazil-power-agent/ docs/superpowers/plans/2026-11-08-brazil-power-gemini-agent-plan.md
git commit -m "feat(brazil-power-agent): add 5 Gemini App skills and customization installer"
```
