# Metadata Governance & 4-Ws Audit Dashboard Design (`Brazil_TT_v13_RJEB`)

**Date:** 2026-11-06  
**Target Service:** `sheets-commodity-mod-gateway` (`comm-model-mod`, `us-central1`)  
**BigQuery Dataset:** `comm-model-mod.sheets_commodity_mod_governance`

---

## 1. Purpose & Scope

Provide a unified, business-friendly consumption layer for structural and cell-level metadata modifications captured in `comm-model-mod.sheets_commodity_mod_governance.audit_events`, delivered across three surfaces:

1. **Lean BigQuery View (`sheets_commodity_mod_governance.vw_audit_dashboard_lean`)**:
   - Excludes `INITIAL_BASELINE_INGESTED` rows permanently so every metric, chart, and table row reflects genuine analyst modifications.
   - Exposes 9 concise, business-friendly columns (`event_time_utc`, `workbook_name`, `tab_name`, `cell_ref`, `change_type_label`, `cell_role_label`, `risk_level`, `change_summary`, `analyst_email`).
2. **Live Cloud Run Governance Dashboard (`/governance` & `/v1/governance/dashboard`)**:
   - Shares the exact Coach / Execution Telemetry pastel aesthetic (warm cream-to-sand canvas `#F2EAE3` → `#E2D7CE`, frosted warm ivory containers `#F4F0EB`, crisp `#FFFFFF` inner cards, pastel periwinkle `#CADCFA` active pills, lavender `#EBE5F8`, mint `#E2F3EB`, peach `#F9EBD2`, and soft rose `#FCE8E8` badges).
   - Linked via a top-bar switcher between **Execution Telemetry (`/telemetry`)** and **Metadata Governance (`/governance`)**.
   - Includes a 1-click **Open in Looker Studio** action button pre-bound to `comm-model-mod.sheets_commodity_mod_governance.vw_audit_dashboard_lean`.
3. **Programmatic Looker (LookML) Package (`brazil-power-v13/looker/`)**:
   - `commodity_governance.model.lkml`: Connection and explore definition for `vw_audit_dashboard_lean`.
   - `vw_audit_dashboard_lean.view.lkml`: Dimensions, timeframes (`1h`, `24h`, `7d`, `30d`), and aggregate measures.
   - `metadata_governance.dashboard.lookml`: Declarative LookML dashboard containing the 4 KPI tiles, 3 bar charts, 9-column table, filters, and Coach pastel hex color palette.

---

## 2. BigQuery View Specification (`vw_audit_dashboard_lean`)

Added to [`brazil-power-v13/sql/bigquery/002_governance_views.sql`](file:///Users/ferozmulla/Desktop/smart-coder/commodity-modeling-sheets-platform/brazil-power-v13/sql/bigquery/002_governance_views.sql) and deployed to `comm-model-mod.sheets_commodity_mod_governance`:

| Column Name | UI Header | SQL Derivation |
| :--- | :--- | :--- |
| `event_id` | *(row key)* | `event_id` |
| `event_time_utc` | **`Time (UTC)`** | `when_event_utc` |
| `workbook_name` | **`Workbook`** | Normalized `workbook_id` (`Brazil_TT_v13_RJEB_Gcloud` or analyst copy name) |
| `spreadsheet_id` | *(filter key)* | `who_spreadsheet_id` |
| `tab_name` | **`Tab`** | `sheet_name` |
| `cell_ref` | **`Cell`** | `REPLACE(cell_coord, '#REF!', 'Grid')` |
| `change_type_code` | *(raw code)* | `what_change_type` |
| `change_type_label` | **`Change Type`** | Mapped to `Manual Override`, `Header / Label Modified`, `Row Inserted`, `Column Inserted`, `Sheet Added`, `Sheet Deleted`, `Formula Modified` |
| `cell_role_label` | **`Role`** | Mapped from `what_semantic_role` to `Formula Cell`, `Static / Label`, `Scenario Input`, `Solver Output` |
| `risk_level` | **`Severity`** | `severity` (`CRITICAL`, `WARNING`, `INFO`) |
| `before_display` | *(before)* | `COALESCE(JSON_VALUE(before_state, '$.formula'), JSON_VALUE(before_state, '$.value'), '—')` |
| `after_display` | *(after)* | `COALESCE(JSON_VALUE(after_state, '$.formula'), JSON_VALUE(after_state, '$.value'), '—')` |
| `change_summary` | **`Before → After`** | Concise formatted transition (`before_display || ' → ' || after_display`) |
| `analyst_email` | **`Analyst`** | `who_google_user` |

Filter clause: `WHERE what_change_type != 'INITIAL_BASELINE_INGESTED'`.

---

## 3. Interactive Filters & Visuals on `/governance`

### 3.1 Top Pill Bar & Filter Controls
- **View Switcher Pill**: Toggle between **`Execution Telemetry`** (`/telemetry`) and **`Metadata Governance`** (`/governance`).
- **Timeframe Filter Pill**: Segmented buttons for **`Last Hour`** (`1h`), **`Last Day`** (`24h`), **`Last Week`** (`7d`), **`Last Month`** (`30d`), and **`All Time`** (`all`).
- **Master Sheet / Workbook Filter**: Dropdown (`All Workbooks` + distinct `workbook_name` values).
- **Analyst Filter**: Dropdown (`All Analysts` + distinct `analyst_email` values).
- **Action Buttons**:
  - **`Open in Looker Studio`**: Opens Looker Studio Linking API pre-configured for `comm-model-mod.sheets_commodity_mod_governance.vw_audit_dashboard_lean`.
  - **`Refresh BQ`**: Forces an immediate BigQuery reload.

### 3.2 Visual Components
1. **Governance KPI Summary Strip (4 Cards)**:
   - **Total Modifications**: Total count of analyst edits in the active filter window.
   - **Critical Overrides**: Count & share of `CRITICAL` (`MANUAL_OVERRIDE` / `SHEET_DELETED`) events.
   - **Top Modified Tab**: Most frequently modified `tab_name` and its share of edits.
   - **Active Copies & Analysts**: Count of distinct workbooks and distinct analysts in the filtered window.
2. **Chart 1 — Most Modified Sheets (Horizontal Bar Chart)**:
   - Ranks `tab_name` by modification count with periwinkle bars (`#CADCFA` fill / `#2B50AA` label). Clicking any bar filters the table to that tab.
3. **Chart 2 — Analyst Modifications by Change Type (Horizontal Bar Chart)**:
   - Ranks `change_type_label` (`Manual Override`, `Header / Label Modified`, `Sheet Added`, `Column Inserted`, `Row Inserted`, `Sheet Deleted`) with semantic pastel bars. Clicking any bar filters the table to that change type.
4. **Chart 3 — Workbook Copy Drift Comparison (Stacked Horizontal Bar Chart)**:
   - Compares modification volume across each workbook copy (`Regional Power Generation... (Governed)`, `New Copy...`, `FHM Copy...`) split into **Critical Overrides** (rose `#E89F9E`) vs. **Structural / Label Edits** (periwinkle `#9DC0F6`). Clicking a bar filters the table to that workbook.
5. **Lean 4-Ws Audit Table (`vw_audit_dashboard_lean`)**:
   - Displays the 9 business-friendly columns (`Time (UTC)`, `Workbook`, `Tab`, `Cell`, `Change Type`, `Role`, `Severity`, `Before → After`, `Analyst`) with instant text search and active chart-filter pills.
