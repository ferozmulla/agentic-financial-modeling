# Brazil Energy Model (v13) — Isolated BigQuery Digital Twin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy `brazil-power-bq-twin`, a 100% isolated BigQuery-backed Digital Twin MCP server and Cowork skill suite for the 22-tab Brazil Power v13 model that executes all assumptions, Tornado IRR, BigQuery ML `ARIMA_PLUS`, 23-year LCOE, 30-year DCF, and 22-tab `.xlsx` / Google Sheets synthesis with zero runtime `.xlsm` dependency.

**Architecture:** A one-time offline compiler (`load_xlsm_to_bq.py`) decomposes the 22-tab workbook—values, formulas, styles, merges, column widths, and solver vectors—into clustered tables in a dedicated BigQuery dataset (`comm-model-mod.brazil_power_digital_twin`). At runtime, a standalone Cloud Run service (`brazil-power-bq-twin-mcp`, built from a `Dockerfile` containing zero Excel files and zero imports from `brazil-power-v13` or `brazil-power-agent`) caches the immutable baseline from BigQuery, overlays sparse session deltas from `dt_scenario_deltas`, executes self-contained NumPy/SciPy solvers + BigQuery ML forecasts, and synthesizes 22-tab `.xlsx` workbooks purely from database rows.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, NumPy, OpenPyXL (workbook synthesis only), `google-cloud-bigquery`, `google-cloud-storage`, `google-api-python-client`, `pytest`.

## Global Constraints

- **Zero Coexistence Coupling**: Never modify any file under `brazil-power-v13/` or `brazil-power-agent/`. Zero Python imports from `src.*` (of `brazil-power-v13`) or `brazil_power_agent.*` inside `brazil-power-bq-twin/`.
- **Zero Runtime Excel Files**: Zero `.xlsm`, `.xlsx`, or `.xls` files inside `brazil-power-bq-twin/` or its Docker build context.
- **Dedicated GCP Resources (`comm-model-mod` / `1024543888590`)**:
  - BigQuery Dataset: `comm-model-mod.brazil_power_digital_twin` (`us-central1`)
  - GCS Prefixes: `gs://comm-model-mod-sheets-mod-artifacts/bq_twin_exports/` and `bq_twin_artifacts/`
  - Cloud Run Service: `brazil-power-bq-twin-mcp` (`us-central1`)
  - Agent Registry MCP Server: `brazil-power-bq-twin-mcp`; Skills: `bq-twin-power-model`, `bq-twin-tornado`, `bq-twin-bqml`, `bq-twin-lcoe`, `bq-twin-dcf`
- **Security & Cost Guardrails**:
  - All BigQuery queries must use `bigquery.ScalarQueryParameter` and set `QueryJobConfig(maximum_bytes_billed=50 * 1024 * 1024)`.
  - All `gcloud` commands must prepend `CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity"`; supported `bq` commands must include `--label datacloud:antigravity`.
  - Download routes must validate filenames against `^[A-Za-z0-9_.\-]+\.(xlsx|md)$`, check `.resolve().is_relative_to(base_dir)`, and set `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`.

---

### Task 1: Package Scaffolding, Domain Models, BigQuery DDL & Strict Isolation Guard

**Files:**
- Create: `brazil-power-bq-twin/pyproject.toml`
- Create: `brazil-power-bq-twin/requirements.txt`
- Create: `brazil-power-bq-twin/Dockerfile`
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/__init__.py`
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/config.py`
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/models.py`
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/schema_ddl.py`
- Test: `brazil-power-bq-twin/tests/test_isolation_guards.py`

**Interfaces:**
- Consumes: Standard library (`ast`, `dataclasses`, `pathlib`), `pydantic_settings`.
- Produces:
  - `config.TwinSettings` (`gcp_project_id="comm-model-mod"`, `bq_dataset="brazil_power_digital_twin"`, `bq_location="us-central1"`, `max_bytes_billed=52428800`, `gcs_bucket="comm-model-mod-sheets-mod-artifacts"`, `workbook_id="brazil_power_v13"`, `default_version_id="v13_baseline"`), `get_twin_settings() -> TwinSettings`
  - `models.StyleRecord`, `models.WorksheetRecord`, `models.CellRecord`, `models.CellDelta`, `models.AuditRow`, `models.BaselineTwinSnapshot`, `models.SessionOverlay`, `models.split_a1_coord(coord: str) -> tuple[str, int]`, `models.col_letter_to_index(col: str) -> int`, `models.index_to_col_letter(idx: int) -> str`
  - `schema_ddl.EXPECTED_22_TABS: tuple[str, ...]`, `schema_ddl.build_digital_twin_ddl_statements(project_id: str, dataset_id: str) -> list[str]`

- [ ] **Step 1: Write the failing test (`brazil-power-bq-twin/tests/test_isolation_guards.py`)**

```python
from __future__ import annotations

import ast
from pathlib import Path

from brazil_power_bq_twin.config import get_twin_settings
from brazil_power_bq_twin.models import col_letter_to_index, index_to_col_letter, split_a1_coord
from brazil_power_bq_twin.schema_ddl import EXPECTED_22_TABS, build_digital_twin_ddl_statements

TWIN_ROOT = Path(__file__).resolve().parents[1]


def test_zero_excel_files_and_zero_cross_package_imports() -> None:
    excel_files = [
        p for p in TWIN_ROOT.rglob("*")
        if p.is_file() and p.suffix.lower() in {".xlsm", ".xlsx", ".xls", ".xlsb"}
    ]
    assert excel_files == [], f"Forbidden Excel files found in brazil-power-bq-twin: {excel_files}"

    dockerfile_text = (TWIN_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "seed/" not in dockerfile_text
    assert ".xlsm" not in dockerfile_text

    forbidden_roots = {"src", "brazil_power_agent"}
    for py_file in (TWIN_ROOT / "src").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_roots
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_roots


def test_settings_coords_and_ddl_generation() -> None:
    settings = get_twin_settings()
    assert settings.bq_dataset == "brazil_power_digital_twin"
    assert settings.max_bytes_billed == 50 * 1024 * 1024
    assert len(EXPECTED_22_TABS) == 22
    assert split_a1_coord("$C$20") == ("C", 20)
    assert index_to_col_letter(col_letter_to_index("AN")) == "AN"

    ddls = build_digital_twin_ddl_statements("comm-model-mod", "brazil_power_digital_twin")
    joined = "\n".join(ddls)
    for obj_name in (
        "dt_workbook_versions",
        "dt_worksheets",
        "dt_styles",
        "dt_cells",
        "dt_scenario_deltas",
        "vw_dt_latest_session_deltas",
        "dt_audit_events",
        "dt_lt_trajectories",
    ):
        assert f"`comm-model-mod.brazil_power_digital_twin.{obj_name}`" in joined
    assert "CLUSTER BY" in joined
    assert "PARTITION BY DATE(" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_isolation_guards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_bq_twin'`

- [ ] **Step 3: Implement scaffolding, `config.py`, `models.py`, `schema_ddl.py`, and `Dockerfile`**

Create `brazil-power-bq-twin/requirements.txt` (`numpy>=1.26.0`, `openpyxl>=3.1.2`, `fastapi>=0.110.0`, `uvicorn[standard]>=0.27.0`, `pydantic>=2.6.0`, `pydantic-settings>=2.2.0`, `google-auth>=2.28.0`, `google-api-python-client>=2.120.0`, `google-cloud-bigquery>=3.17.0`, `google-cloud-storage>=2.14.0`), `Dockerfile` copying only `requirements.txt` and `src/` (running as non-root `appuser` with `/tmp/bq_twin_exports` and `/tmp/bq_twin_artifacts`), `config.py`, `models.py` (with frozen/mutable dataclasses for `StyleRecord`, `WorksheetRecord`, `CellRecord`, `CellDelta`, `AuditRow`, `BaselineTwinSnapshot`, `SessionOverlay`, and A1 coordinate helpers), and `schema_ddl.py` generating clustered/partitioned `CREATE TABLE IF NOT EXISTS` and `CREATE OR REPLACE VIEW` statements for `comm-model-mod.brazil_power_digital_twin`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_isolation_guards.py -v`
Expected: PASS (`2 passed`)

- [ ] **Step 5: Commit**

```bash
git add brazil-power-bq-twin/
git commit -m "feat(bq-twin): scaffold isolated package, domain models, BigQuery DDL, and isolation guards"
```

---

### Task 2: `DigitalTwinStore` (`InMemoryDigitalTwinStore` & `BigQueryDigitalTwinStore`)

**Files:**
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/bq_store.py`
- Test: `brazil-power-bq-twin/tests/test_bq_store.py`

**Interfaces:**
- Consumes: `config.TwinSettings`, `models.*`, `google.cloud.bigquery`
- Produces:
  - `DigitalTwinStore` (Protocol):
    - `get_baseline_snapshot(version_id: str = "v13_baseline") -> BaselineTwinSnapshot`
    - `get_session_overlay(session_id: str, version_id: str = "v13_baseline") -> SessionOverlay`
    - `append_session_deltas(session_id: str, deltas: list[CellDelta], audit_rows: list[AuditRow] | None = None, version_id: str = "v13_baseline") -> None`
    - `reset_session(session_id: str, version_id: str = "v13_baseline") -> None`
    - `fetch_bqml_trajectories() -> dict[str, Any]`
  - `InMemoryDigitalTwinStore(snapshot: BaselineTwinSnapshot, lt_trajectories: dict[str, Any] | None = None)`
  - `BigQueryDigitalTwinStore(settings: TwinSettings | None = None, bq_client: Any | None = None)`
  - `resolve_effective_cell_value(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay, sheet_name: str, coord: str) -> Any`
  - `resolve_effective_grid(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay, sheet_name: str, start_coord: str, end_coord: str) -> list[list[Any]]`

- [ ] **Step 1: Write the failing test (`brazil-power-bq-twin/tests/test_bq_store.py`)**

Write tests verifying:
1. `InMemoryDigitalTwinStore` overlays `USER_OVERRIDE` and `SOLVED_OUTPUT` deltas onto `BaselineTwinSnapshot`, supports `reset_session` (`RESET_TOMBSTONE` restores baseline value), and resolves rectangular grids (`General!C5:N40`).
2. `BigQueryDigitalTwinStore` builds parameterized `QueryJobConfig` calls (`ScalarQueryParameter("version_id", "STRING", ...)` and `ScalarQueryParameter("session_id", "STRING", ...)`) with `maximum_bytes_billed == 50 * 1024 * 1024` and maintains a write-through session cache for immediate read-after-write consistency.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_bq_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_bq_twin.bq_store'`

- [ ] **Step 3: Implement `bq_store.py`**

Implement `InMemoryDigitalTwinStore`, `BigQueryDigitalTwinStore` (using `ScalarQueryParameter`, `maximum_bytes_billed`, `@lru_cache` baseline caching, write-through `session_id` overlay cache, and `insert_rows_json` for append-only `dt_scenario_deltas` and `dt_audit_events`), `resolve_effective_cell_value`, and `resolve_effective_grid`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-bq-twin/src/brazil_power_bq_twin/bq_store.py brazil-power-bq-twin/tests/test_bq_store.py
git commit -m "feat(bq-twin): add parameterized BigQueryDigitalTwinStore and InMemoryDigitalTwinStore"
```

---

### Task 3: Offline `.xlsm` Decompiler & BigQuery Batch Loader (`xlsm_compiler.py` & `load_xlsm_to_bq.py`)

**Files:**
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/xlsm_compiler.py`
- Create: `brazil-power-bq-twin/scripts/load_xlsm_to_bq.py`
- Test: `brazil-power-bq-twin/tests/test_xlsm_compiler.py`

**Interfaces:**
- Consumes: `openpyxl` (offline CLI / synthetic test workbook in `tmp_path` only), `models.*`, `schema_ddl.*`
- Produces:
  - `CompiledTwinPayload` dataclass (`version_row: dict`, `worksheet_rows: list[dict]`, `style_rows: list[dict]`, `cell_rows: list[dict]`, `lt_trajectory_rows: list[dict]`, `snapshot: BaselineTwinSnapshot`)
  - `compile_workbook_to_twin_payload(workbook_path: Path, workbook_id: str = "brazil_power_v13", version_id: str = "v13_baseline") -> CompiledTwinPayload`
  - `scripts/load_xlsm_to_bq.py`: CLI accepting `--xlsm-path`, `--project-id`, `--dataset-id`, creating dataset/tables/views and loading rows via `bigquery.Client.load_table_from_json` (`WRITE_TRUNCATE` for baseline tables) + training `ARIMA_PLUS` model `bqml_dt_lt_forecast` and creating `vw_lt_forecasts`.

- [ ] **Step 1: Write the failing test (`brazil-power-bq-twin/tests/test_xlsm_compiler.py`)**

Build a synthetic multi-sheet `.xlsx` in `tmp_path` (at test runtime, so zero Excel files sit in the repo) containing styled numeric inputs, `=SUM(...)` formulas, merged headers, custom column widths, `General`, `LT Capex`, `LT Fuel`, `LT CF`, and `_01_CF.._12_CF` tabs, and assert `compile_workbook_to_twin_payload` extracts deduplicated `style_rows`, exact `raw_formula` strings (without leading `=`), cached numeric values, `merged_ranges_json`, `col_widths_json`, and `solver_parameters`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_xlsm_compiler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brazil_power_bq_twin.xlsm_compiler'`

- [ ] **Step 3: Implement `xlsm_compiler.py` and `scripts/load_xlsm_to_bq.py`**

Open the workbook twice (`data_only=False` for formulas/styles/merges/widths/named ranges and `data_only=True` for cached formula evaluation values), deduplicate style tuples into integer `style_id`s, classify `semantic_role` (`INPUT`, `FORMULA`, `LABEL`, `OUTPUT`), extract per-technology solver baseline parameters (`_01_CF.._12_CF` CAPEX, capacity, CF, heat rate, fuel, O&M, WACC, debt/equity, loan tenor, tax, lead time, economic life, Tornado low/base/high vectors), and implement the BigQuery batch loader CLI in `scripts/load_xlsm_to_bq.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-bq-twin/src/brazil_power_bq_twin/xlsm_compiler.py brazil-power-bq-twin/scripts/load_xlsm_to_bq.py brazil-power-bq-twin/tests/test_xlsm_compiler.py
git commit -m "feat(bq-twin): add offline xlsm-to-BigQuery Digital Twin compiler and batch loader"
```

---

### Task 4: Self-Contained Quantitative Solver & Markdown/ECharts Renderer (`solver_engine.py` & `renderer.py`)

**Files:**
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/solver_engine.py`
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/renderer.py`
- Test: `brazil-power-bq-twin/tests/test_solver_parity.py`

**Interfaces:**
- Consumes: `models.*`, `bq_store.resolve_effective_grid`, `numpy`
- Produces:
  - `TECH_CATALOG: dict[str, dict[str, Any]]` (`_01_CF.._12_CF` labels, columns, thermal/renewable/DG classification)
  - `QuantitativeTwinSolver`:
    - `extract_assumptions(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay, technologies: list[str] | None = None) -> dict[str, Any]`
    - `stage_overrides(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay, overrides: dict[str, Any]) -> tuple[list[CellDelta], list[AuditRow], list[dict[str, Any]]]`
    - `run_tornado_sensitivity(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay, technology_code: str = "_06_CF") -> tuple[dict[str, Any], list[CellDelta]]`
    - `run_lcoe_horizon(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay) -> tuple[dict[str, Any], list[CellDelta]]`
    - `run_dcf_and_cvu(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay, technology_code: str = "_01_CF", start_year: int = 2024, end_year: int = 2053, include_cvu_sweep: bool | None = None) -> tuple[dict[str, Any], list[CellDelta]]`
  - `TwinMarkdownAndChartRenderer`:
    - Formats inline Excel-coordinate Markdown tables, full multi-line Side-Pane Artifact Markdown tables (guaranteed physical `\n` per row), and Apache ECharts V5 option dictionaries (`horizontal bar Tornado`, `multi-series LCOE line`, `BQML trajectory line`, `30-year DCF cash-flow + cumulative NPV`).

- [ ] **Step 1: Write the failing test (`brazil-power-bq-twin/tests/test_solver_parity.py`)**

Write tests constructing a `BaselineTwinSnapshot` + `InMemoryDigitalTwinStore` and asserting:
1. `stage_overrides({"_01_CF": {"fuel_cost": 6.50}, "General!H14": 2.0})` produces exact `CellDelta` coordinates (`General!C20`, `General!H14`) and shifts solved IRR/LCOE monotonically in the expected economic direction (higher fuel cost lowers Gas CCGT IRR and raises LCOE; shorter SHP construction lead time raises SHP IRR).
2. `run_tornado_sensitivity` solves 21 points per 7-parameter sheet (`_01_CF.._10_CF`) or 12 points for DG (`_11_CF.._12_CF`) and emits `_0N_CF!E6:G12` + `Output_1` `CellDelta`s and valid ECharts JSON.
3. `run_lcoe_horizon` solves all 23 years (`2024..2046`) across `Output_3!B9:J31` and emits `CellDelta`s.
4. `run_dcf_and_cvu` computes 30-year project & equity cash flows (`2024..2053`), NPV, Project IRR, Equity IRR, Payback, and 10-point `CVU_GF` thermal sweep.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_solver_parity.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `solver_engine.py` and `renderer.py`**

Implement self-contained Newton-Raphson / bisection IRR & binary-search tariff/LCOE solvers, 30-year SAC/PRICE debt amortization + Brazilian 34% IRPJ/CSLL corporate tax + depreciation shield cash-flow engine, 21-point Tornado sweep, 10-point CVU/GF sweep, and `TwinMarkdownAndChartRenderer` with zero imports outside `brazil_power_bq_twin`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-bq-twin/src/brazil_power_bq_twin/solver_engine.py brazil-power-bq-twin/src/brazil_power_bq_twin/renderer.py brazil-power-bq-twin/tests/test_solver_parity.py
git commit -m "feat(bq-twin): add self-contained Tornado, LCOE, and 30-year DCF solver engine and ECharts renderer"
```

---

### Task 5: Zero-Template 22-Tab `.xlsx` & Google Sheets Synthesizer (`xlsx_synthesizer.py`)

**Files:**
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/xlsx_synthesizer.py`
- Test: `brazil-power-bq-twin/tests/test_xlsx_synthesizer.py`

**Interfaces:**
- Consumes: `models.*`, `bq_store.DigitalTwinStore`, `openpyxl`
- Produces:
  - `sanitize_filename(name: str, expected_ext: str) -> str`
  - `synthesize_22tab_xlsx_bytes(snapshot: BaselineTwinSnapshot, overlay: SessionOverlay) -> tuple[bytes, dict[str, Any]]`
  - `export_digital_twin_workbook(store: DigitalTwinStore, session_id: str, export_format: str = "xlsx", output_filename: str | None = None, output_dir: Path | None = None, sheet_title: str | None = None, cloud_base_url: str | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test (`brazil-power-bq-twin/tests/test_xlsx_synthesizer.py`)**

Write tests asserting that `synthesize_22tab_xlsx_bytes` constructs a valid 22-tab `.xlsx` workbook in memory from `BaselineTwinSnapshot` + `SessionOverlay` (with zero template file on disk), preserving all 22 sheet names in order, reconstructing `=SUM(...)` formulas on unmodified formula cells, overwriting overridden/solved cells with `SessionOverlay` values, applying `number_format` and bold `Font` from `StyleRecord`, applying `merged_ranges`, and rejecting `../` traversal filenames via `sanitize_filename`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_xlsx_synthesizer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `xlsx_synthesizer.py`**

Implement `synthesize_22tab_xlsx_bytes` (instantiating `openpyxl.Workbook()`, removing default sheet, creating each `WorksheetRecord` in `sheet_index` order, hydrating `openpyxl.styles.{Font, PatternFill, Border, Side, Alignment}`, writing cells with `delta -> =raw_formula -> literal` precedence, applying column widths, row heights, freeze panes, and merged cells) plus GCS `bq_twin_exports/` upload and pure `spreadsheets.create` + `values.batchUpdate` 22-tab Google Sheets creation.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brazil-power-bq-twin/src/brazil_power_bq_twin/xlsx_synthesizer.py brazil-power-bq-twin/tests/test_xlsx_synthesizer.py
git commit -m "feat(bq-twin): add pure database-to-xlsx and Google Sheets 22-tab synthesizer"
```

---

### Task 6: Full-Duplex Remote SSE MCP Server, Download Endpoints & Cowork Skills

**Files:**
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/mcp_tools.py`
- Create: `brazil-power-bq-twin/src/brazil_power_bq_twin/mcp_app.py`
- Create: `brazil-power-bq-twin/skills/bq-twin-power-model/SKILL.md`
- Create: `brazil-power-bq-twin/skills/bq-twin-tornado/SKILL.md`
- Create: `brazil-power-bq-twin/skills/bq-twin-bqml/SKILL.md`
- Create: `brazil-power-bq-twin/skills/bq-twin-lcoe/SKILL.md`
- Create: `brazil-power-bq-twin/skills/bq-twin-dcf/SKILL.md`
- Test: `brazil-power-bq-twin/tests/test_mcp_sse_and_security.py`

**Interfaces:**
- Consumes: `bq_store.*`, `solver_engine.*`, `renderer.*`, `xlsx_synthesizer.*`, `fastapi`
- Produces:
  - `MCP_SERVER_NAME = "brazil-power-bq-twin-mcp"`, `TWIN_MCP_TOOLS: list[dict[str, Any]]` (7 tools)
  - `handle_twin_jsonrpc(request: dict[str, Any], store: DigitalTwinStore, session_id: str) -> dict[str, Any] | None`
  - `create_twin_mcp_app(store: DigitalTwinStore | None = None) -> FastAPI` exposing `GET /health`, `POST /mcp`, `GET /mcp/sse`, `POST /mcp/messages`, `GET /v1/exports/{filename}`, `GET /v1/artifacts/{filename}`

- [ ] **Step 1: Write the failing test (`brazil-power-bq-twin/tests/test_mcp_sse_and_security.py`)**

Test `create_twin_mcp_app(store=in_memory_store)` with `TestClient`:
1. `GET /health` returns `{"status": "ok", "backend": "bigquery_digital_twin", "excel_files_used": 0}`.
2. `POST /mcp` executes `initialize`, `tools/list` (7 tools), `tools/call` (`get_session_assumptions`, `update_session_assumptions`, `run_tornado_sensitivity`, `export_full_22tab_workbook`).
3. `GET /mcp/sse?session_id=s1&once=1` and `POST /mcp/messages?session_id=s2` push JSON-RPC frames onto `_ACTIVE_SSE_QUEUES`.
4. `/v1/exports/{filename}` and `/v1/artifacts/{filename}` serve synthesized files with `X-Content-Type-Options: nosniff` and `Content-Disposition: attachment` and block `..%2F` traversal with HTTP `400`/`404`.
5. All 5 `skills/bq-twin-*/SKILL.md` files contain valid YAML frontmatter and reference `brazil-power-bq-twin-mcp`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/test_mcp_sse_and_security.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `mcp_tools.py`, `mcp_app.py`, and the 5 `skills/bq-twin-*/SKILL.md` files**

Implement the 7 MCP tools backed purely by `DigitalTwinStore`, full-duplex SSE queue (`_ACTIVE_SSE_QUEUES`) with 15s keepalives, hardened download endpoints, and the 5 isolated Cowork `SKILL.md` files (preserving the standalone Step 1 `write_to_file` -> Step 2 `ask_question` gate on Turn 1).

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/ -v`
Expected: PASS (including `test_isolation_guards.py` across all newly added files!)

- [ ] **Step 5: Commit**

```bash
git add brazil-power-bq-twin/
git commit -m "feat(bq-twin): add FastAPI full-duplex SSE MCP server, hardened downloads, and 5 isolated Cowork skills"
```

---

### Task 7: Live BigQuery Digital Twin Ingestion, Cloud Run Deployment & Agent Registry Publication

**Files:**
- Create: `brazil-power-bq-twin/scripts/publish_bq_twin_registry.py`
- Create: `brazil-power-bq-twin/scripts/install_bq_twin_cowork.py`

**Interfaces:**
- Consumes: `scripts/load_xlsm_to_bq.py`, `mcp_tools.TWIN_MCP_TOOLS`, `https://agentregistry.googleapis.com/mcp`, `gcloud run deploy`
- Produces:
  - Populated BigQuery dataset `comm-model-mod.brazil_power_digital_twin` (`dt_workbook_versions`, `dt_worksheets`, `dt_styles`, `dt_cells`, `dt_scenario_deltas`, `vw_dt_latest_session_deltas`, `dt_audit_events`, `dt_lt_trajectories`, `bqml_dt_lt_forecast`, `vw_lt_forecasts`)
  - Deployed Cloud Run service `brazil-power-bq-twin-mcp` (`us-central1`, zero `.xlsm` in image)
  - Registered Agent Registry MCP Server (`brazil-power-bq-twin-mcp`) + 5 `STATE_ACTIVE` Skills (`private-bq-twin-*`)

- [ ] **Step 1: Implement `publish_bq_twin_registry.py` and `install_bq_twin_cowork.py`**

Create `publish_bq_twin_registry.py` (idempotent `create_service`/`update_service` for `brazil-power-bq-twin-mcp` and `create_skill`/`create_skill_revision` for `bq-twin-power-model`, `bq-twin-tornado`, `bq-twin-bqml`, `bq-twin-lcoe`, `bq-twin-dcf` on `https://agentregistry.googleapis.com/mcp`) and `install_bq_twin_cowork.py` (optional `--enable` / `--disable` helper to register `brazil-power-bq-twin-mcp` via `serverUrl` alongside `brazil-power-mcp` in `~/.gemini/config/mcp_config.json` without overwriting `brazil-power-mcp`).

- [ ] **Step 2: Run one-time BigQuery ingestion (`load_xlsm_to_bq.py`)**

Run:
```bash
PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/python brazil-power-bq-twin/scripts/load_xlsm_to_bq.py \
  --xlsm-path brazil-power-v13/seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm \
  --project-id comm-model-mod \
  --dataset-id brazil_power_digital_twin
```
Expected: Dataset created, 22 worksheets + ~150 styles + ~18,000 cells batch-loaded into `comm-model-mod.brazil_power_digital_twin`, and `ARIMA_PLUS` forecast view `vw_lt_forecasts` created.

- [ ] **Step 3: Deploy `brazil-power-bq-twin-mcp` to Google Cloud Run (`us-central1`)**

Run:
```bash
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
  gcloud run deploy brazil-power-bq-twin-mcp \
  --source brazil-power-bq-twin \
  --project comm-model-mod \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account sa-sheets-gateway@comm-model-mod.iam.gserviceaccount.com \
  --quiet
```
Expected: Service deployed and serving 100% traffic at `https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app`.

- [ ] **Step 4: Register in Agent Registry & Verify Live End-to-End SSE + DB-Synthesized `.xlsx`**

Run `publish_bq_twin_registry.py`, verify `brazil-power-bq-twin-mcp` (`7` tools) and all 5 `private-bq-twin-*` skills reach `STATE_ACTIVE` in Agent Registry, and execute a live SSE handshake + `run_tornado_sensitivity` + `export_full_22tab_workbook` against Cloud Run confirming a 22-tab `.xlsx` is synthesized purely from BigQuery rows (`excel_files_used: 0`).

- [ ] **Step 5: Run full isolation & regression test suites across the monorepo and commit**

```bash
PYTHONPATH=brazil-power-bq-twin/src ./.venv/bin/pytest brazil-power-bq-twin/tests/ -v
PYTHONPATH=brazil-power-agent/src:brazil-power-v13 ./.venv/bin/pytest brazil-power-agent/tests/ -q
git add brazil-power-bq-twin/
git commit -m "feat(bq-twin): deploy isolated BigQuery Digital Twin MCP server to Cloud Run and register in Agent Registry"
```
