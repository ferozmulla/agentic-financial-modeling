# Commodity Modeling Sheets Platform

Multi-workbook modernization platform migrating complex desktop Excel/VBA (`*.xlsm`) commodity and energy valuation models onto **Google Sheets**, **Cloud Run**, **BigQuery / BigQuery ML**, and **Vertex AI**, with silent **4-Ws (`Who`, `What`, `When`, `Why`)** formula and structural governance.

Each modernized workbook lives in its own self-contained sub-folder with isolated seed fixtures, vectorized solver routines, container-bound Google Apps Script modules, BigQuery ML views, Terraform IaC, documentation, and parity test suites.

---

## Modernized Workbooks Catalog

| Sub-Folder | Workbook / Domain | Status | Live GCP / Workspace Target |
| :--- | :--- | :--- | :--- |
| [`brazil-power-v13/`](./brazil-power-v13/README.md) | **Regional Power Generation Techno-Economic Model — Brazil (`v13`)**<br>`22` core tabs (`15,961` formulas), `31` 3D Cloud Solver buttons (`854` parity-verified outputs), `3` live BQML `ARIMA_PLUS` forecast tabs (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`), and distributed `4-Ws` governance | **Live & Verified** (`30/30` tests passing) | Project: `comm-model-mod` (`us-central1`)<br>Sheet ID: `1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI` |

---

## Repository Layout

```text
commodity-modeling-sheets-platform/
├── README.md                    # Platform index & multi-workbook catalog
├── Makefile                     # Root convenience targets across workbook sub-projects
├── .gitignore                   # Shared ignore rules (virtualenv, caches, local DBs, secrets)
├── .venv/                       # Shared Python 3.11+ virtual environment
└── brazil-power-v13/            # Self-contained Brazil Power Generation v13 modernization
    ├── README.md                # Architecture, live endpoints & quickstart
    ├── apps_script/             # Container-bound Google Apps Script (Menu, Solver, AuditHooks)
    ├── docs/                    # PRD, Design Doc, Implementation Plan & Leadership Demo Runbook
    ├── infra/terraform/         # GCP Infrastructure-as-Code (us-central1)
    ├── scripts/                 # Sheet seeding, 3D button styling & BQML deployment scripts
    ├── seed/                    # Read-only baseline .xlsm workbook
    ├── sql/bigquery/            # Governance DDL, 4-Ws views & BQML ARIMA_PLUS / surrogate SQL
    ├── src/                     # FastAPI gateway, vectorized solver & AST/DAG governance engine
    └── tests/                   # Unit, 854-cell parity, AST/DAG, E2E & Terraform test suites
```

---

## Adding a New Workbook Modernization

1. Create a new sibling directory at the root (for example, `<region-or-commodity-model>/`) following the self-contained layout in [`brazil-power-v13/`](./brazil-power-v13/README.md).
2. Reuse the shared `.venv/` at the platform root (or create a workbook-specific `.venv/` if dependencies diverge).
3. Register the new sub-folder in the **Modernized Workbooks Catalog** table above and add corresponding `test-<name>` / `lint-<name>` targets in the root [`Makefile`](./Makefile).

---

## Root Quickstart Commands

```bash
# Run lint + all 30 parity, governance, E2E, and Terraform tests for Brazil Power v13
make check-brazil

# Or work directly inside a specific workbook folder
make -C brazil-power-v13 lint
make -C brazil-power-v13 test
```
