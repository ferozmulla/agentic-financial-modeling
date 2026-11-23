---
name: energy-twin-builder
description: "Autonomous sandbox builder skill for decompiling an Energy modeling spreadsheet (.xlsx/.xlsm), scaffolding an isolated BigQuery Digital Twin + 4-Ws Governance + ARIMA_PLUS BQML + custom Python/VBA Solver + Remote MCP Server, and verifying numeric parity via pytest."
---

# Energy Digital Twin Autonomous Builder (`energy-twin-builder`)

Follow these exact steps inside the Managed Agents sandbox to build and verify `<model_slug>-bq-twin/`:

## 1. Environment Bootstrap
1. Install runtime verification libraries if not already present:
   ```bash
   python3 -m pip install --quiet openpyxl pytest fastapi pydantic pydantic-settings numpy scipy pyyaml
   ```
2. Read `/.agent/job/input/hygiene_exception_report.json` and `/.agent/job/input/vba_modules/vba_manifest.json` (if present) to inspect:
   - `model_slug`, `archetype`, `is_iterative_calc`, `iterate_count`
   - `candidate_assumption_sheets`, `candidate_timeseries_sheets`, `vba_modules`, and `exceptions`

## 2. Package Layout (`/.agent/job/output/<model_slug>-bq-twin/`)
Create a self-contained Python package (with `<pkg_name> = model_slug.replace("-", "_") + "_bq_twin"`):
```text
<model_slug>-bq-twin/
├── Dockerfile                     # Non-root Python 3.11-slim (ZERO .xlsx/.xlsm copied)
├── README.md
├── pyproject.toml
├── requirements.txt
├── scripts/
│   ├── load_to_bq.py              # Compiles GCS Golden Vault workbook -> BigQuery dt_* + ARIMA_PLUS
│   └── publish_registry.py        # Publishes MCP server + skills to Agent Registry
├── skills/
│   └── <model_slug>-model-gcp/
│       └── SKILL.md               # Guided Gemini Agent skill for the new Digital Twin
├── src/<pkg_name>/
│   ├── __init__.py
│   ├── config.py                  # Pydantic BaseSettings with ^[A-Za-z0-9_\-]+$ identifier validation
│   ├── models.py                  # Baseline snapshot, cell, style, and delta dataclasses
│   ├── schema_ddl.py              # Partitioned/clustered dt_*, 4-Ws dt_audit_events, ARIMA_PLUS DDL
│   ├── bq_store.py                # Parameterized BigQuery queries (ScalarQueryParameter only; zero SQL concat)
│   ├── xlsx_compiler.py           # OpenXML + style + formula + trajectory extractor
│   ├── solver_engine.py           # Custom AST/circular evaluator + translated VBA GoalSeek/solver routines (zero eval())
│   ├── xlsx_synthesizer.py        # Pure-DB openpyxl synthesizer with strict path-traversal containment
│   ├── mcp_tools.py               # JSON-RPC MCP tool schemas & dispatcher
│   └── mcp_app.py                 # Streamable HTTP POST /mcp + GET /healthz with nosniff/CSP headers
└── tests/
    └── test_parity.py             # Offline numeric parity suite against /.agent/job/input/<workbook>
```

Use the reference templates in `/.agent/skills/energy-twin-builder/templates/` as your starting baseline for `schema_ddl.py`, `bq_store.py`, `xlsx_synthesizer.py`, and `Dockerfile`.

## 3. Mandatory Security & Fidelity Rules
- **Zero `eval()` / `exec()`**: All formula evaluation and VBA translations in `solver_engine.py` must be pure deterministic Python / NumPy / SciPy (`brentq` / `newton` for `GoalSeek`).
- **Zero SQL Concatenation on Runtime Inputs**: Always use parameterized BigQuery `ScalarQueryParameter` in `bq_store.py` and regex `^[A-Za-z0-9_\-]+$` validation on `project_id` and `dataset_id` in `schema_ddl.py`.
- **Zero Workbook Binaries or Secrets in Output**: Never copy `.xlsx`, `.xlsm`, `.pem`, `.key`, or credentials into `/.agent/job/output/<model_slug>-bq-twin/`. In `test_parity.py`, read the workbook path from `os.environ["ONBOARD_SEED_WORKBOOK_PATH"]` (defaulting to `/.agent/job/input/<workbook_name>` inside the sandbox).

## 4. Iterative Parity Verification Loop (`pytest`)
1. Run `ONBOARD_SEED_WORKBOOK_PATH="/.agent/job/input/<workbook_name>" python3 -m pytest /.agent/job/output/<model_slug>-bq-twin/tests -v`.
2. Compare solved/evaluated output cells across target KPI sheets against cached Excel baseline values (`rtol=1e-4, atol=1e-4`).
3. If any parity assertion fails, inspect the cell coordinate, Excel formula / VBA macro, and intermediate values, patch `solver_engine.py` or `xlsx_compiler.py`, and re-run `pytest` until tests pass.
4. Write `/.agent/job/output/parity_report.json` conforming to:
   ```json
   {
     "model_slug": "<model_slug>",
     "passed": true,
     "pytest_passed": 8,
     "pytest_failed": 0,
     "total_compared_cells": 500,
     "total_matched_cells": 500,
     "parity_rate_pct": 100.0,
     "max_abs_error": 0.000001,
     "max_rel_error": 0.000002,
     "sheet_summaries": [
       {
         "sheet_name": "Summary",
         "compared_cells": 500,
         "matched_cells": 500,
         "mismatched_cells": 0,
         "max_abs_error": 0.000001,
         "max_rel_error": 0.000002
       }
     ],
     "documented_irreducible_exceptions": []
   }
   ```
5. Also write a concise Markdown summary to `/.agent/job/output/parity_verification_report.md`.
