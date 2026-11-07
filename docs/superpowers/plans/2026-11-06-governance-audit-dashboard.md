# Metadata Governance & 4-Ws Audit Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy the BigQuery lean audit view (`vw_audit_dashboard_lean`), programmatic LookML package (`brazil-power-v13/looker/`), and live Coach-styled Cloud Run Governance Dashboard (`/governance`) with top-bar switcher from `/telemetry`.

**Architecture:** A BigQuery SQL view (`sheets_commodity_mod_governance.vw_audit_dashboard_lean`) permanently excludes `INITIAL_BASELINE_INGESTED` rows and maps the 19 technical columns of `audit_events` into 9 business-friendly columns. A new FastAPI route module (`src/api/routes/governance_dashboard.py`) serves `/governance`, `/governance/styles.css`, `/governance/app.js`, and `/v1/governance/dashboard` (querying BigQuery with a short TTL cache and fallback to local/seed records in tests), while LookML `.model.lkml`, `.view.lkml`, and `.dashboard.lookml` files provide full Looker Core dashboard-as-code parity.

**Tech Stack:** Python 3.11, FastAPI, Google Cloud BigQuery, LookML, Vanilla JS/CSS (Coach Pastel Palette).

## Global Constraints

- Exclude `INITIAL_BASELINE_INGESTED` rows permanently (`WHERE what_change_type != 'INITIAL_BASELINE_INGESTED'`).
- Use the Coach / Telemetry UI color palette (`#F2EAE3` → `#E2D7CE` cream/sand canvas, `#F4F0EB` frosted ivory panels, `#FFFFFF` inner cards, `#CADCFA` periwinkle active pills, `#EBE5F8` lavender, `#E2F3EB` mint, `#F9EBD2` peach, `#FCE8E8` rose).
- Provide top-bar navigation switcher between `/telemetry` (`Execution Telemetry`) and `/governance` (`Metadata Governance`).

---

### Task 1: BigQuery View `vw_audit_dashboard_lean` & LookML Package

**Files:**
- Modify: `brazil-power-v13/sql/bigquery/002_governance_views.sql`
- Create: `brazil-power-v13/looker/commodity_governance.model.lkml`
- Create: `brazil-power-v13/looker/vw_audit_dashboard_lean.view.lkml`
- Create: `brazil-power-v13/looker/metadata_governance.dashboard.lookml`

- [x] **Step 1: Add `vw_audit_dashboard_lean` to `002_governance_views.sql` and apply in BigQuery**
- [x] **Step 2: Create LookML model, view, and Coach-themed dashboard files in `brazil-power-v13/looker/`**

---

### Task 2: Live Cloud Run `/governance` Dashboard & Top-Bar Navigation Switcher

**Files:**
- Create: `brazil-power-v13/src/api/routes/governance_dashboard.py`
- Modify: `brazil-power-v13/src/api/routes/telemetry.py`
- Modify: `brazil-power-v13/src/main.py`
- Modify: `brazil-power-v13/tests/integration/test_execution_telemetry.py`

- [x] **Step 1: Create `/v1/governance/dashboard` and `/governance` UI in `governance_dashboard.py`**
- [x] **Step 2: Add top-bar switcher between `Execution Telemetry` (`/telemetry`) and `Metadata Governance` (`/governance`)**
- [x] **Step 3: Register `governance_dashboard.router` in `src/main.py` and add integration tests**
- [x] **Step 4: Run `make check-brazil` and deploy `sheets-commodity-mod-gateway` to Cloud Run**
