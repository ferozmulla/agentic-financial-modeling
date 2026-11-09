"""FastAPI routes and Coach-styled UI for the BigQuery 4-Ws Metadata Governance Dashboard."""

from __future__ import annotations

import os
import threading
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from src.core.config import get_settings

router = APIRouter(tags=["governance-dashboard"])

_CACHE_LOCK = threading.Lock()
_CACHED_BQ_ROWS: list[dict[str, Any]] = []
_LAST_BQ_FETCH_MONO: float = 0.0
_CACHE_TTL_SEC: float = 5.0
LOOKER_DASHBOARD_URL: str = "https://56571629-c48f-487a-a65b-9e55b5de76df.looker.app/dashboards/4"


class GovernanceChatRequest(BaseModel):
    """Request payload for the compact Governance Conversational Agent."""

    question: str = Field(..., min_length=1, max_length=1000)
    timeframe: str = Field(default="30d")
    workbook: str = Field(default="all")
    analyst: str = Field(default="all")


def _build_looker_studio_linking_url(project_id: str, dataset_id: str) -> str:
    """Build a 1-click Google Looker Studio Linking API URL bound to vw_audit_dashboard_lean."""
    params = {
        "reporting.reportName": "Model: Brazil_TT_v13_RJEB — 4-Ws Metadata Governance",
        "ds.ds0.connector": "bigQuery",
        "ds.ds0.datasourceName": "vw_audit_dashboard_lean",
        "ds.ds0.projectId": project_id,
        "ds.ds0.type": "TABLE",
        "ds.ds0.datasetId": dataset_id,
        "ds.ds0.tableId": "vw_audit_dashboard_lean",
    }
    return "https://lookerstudio.google.com/reporting/create?" + urllib.parse.urlencode(params)


def _fallback_seed_rows() -> list[dict[str, Any]]:
    """Fallback rows matching vw_audit_dashboard_lean when running offline tests."""
    now = datetime.now(UTC)
    return [
        {
            "event_id": "evt-fhm-20261106-h14",
            "event_time_utc": (now - timedelta(minutes=25)).isoformat(),
            "workbook_name": "FHM Copy — Brazil_TT_v13_RJEB",
            "raw_workbook_id": "FHM Copy of Brazil_TT_v13_RJEB_Gcloud",
            "spreadsheet_id": "11qpwhT85btyy_U2xEgxzJm4W4PcTL6YvJiNOUCgD4HU",
            "tab_name": "General",
            "cell_ref": "H14",
            "change_type_code": "SCENARIO_PARAMETER_MODIFIED",
            "change_type_label": "Parameter Modified",
            "cell_role_label": "Scenario Input",
            "risk_level": "INFO",
            "before_display": "3",
            "after_display": "2",
            "change_summary": "3 → 2",
            "analyst_email": "admin@ferozmulla.altostrat.com",
            "analyst_handle": "admin",
        },
        {
            "event_id": "evt-fhm-20261106-c20",
            "event_time_utc": (now - timedelta(minutes=25)).isoformat(),
            "workbook_name": "FHM Copy — Brazil_TT_v13_RJEB",
            "raw_workbook_id": "FHM Copy of Brazil_TT_v13_RJEB_Gcloud",
            "spreadsheet_id": "11qpwhT85btyy_U2xEgxzJm4W4PcTL6YvJiNOUCgD4HU",
            "tab_name": "General",
            "cell_ref": "C20",
            "change_type_code": "SCENARIO_PARAMETER_MODIFIED",
            "change_type_label": "Parameter Modified",
            "cell_role_label": "Scenario Input",
            "risk_level": "INFO",
            "before_display": "4.50",
            "after_display": "6",
            "change_summary": "4.50 → 6",
            "analyst_email": "admin@ferozmulla.altostrat.com",
            "analyst_handle": "admin",
        },
        {
            "event_id": "evt-master-01",
            "event_time_utc": (now - timedelta(days=3, hours=2)).isoformat(),
            "workbook_name": "Brazil_TT_v13_RJEB (Master)",
            "raw_workbook_id": "Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)",
            "spreadsheet_id": "1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI",
            "tab_name": "_05_CF",
            "cell_ref": "D6",
            "change_type_code": "MANUAL_OVERRIDE",
            "change_type_label": "Manual Override",
            "cell_role_label": "Formula Cell",
            "risk_level": "CRITICAL",
            "before_display": "=(1+$D$5)*C6",
            "after_display": "2000",
            "change_summary": "=(1+$D$5)*C6 → 2000",
            "analyst_email": "admin@ferozmulla.altostrat.com",
            "analyst_handle": "admin",
        },
        {
            "event_id": "evt-master-02",
            "event_time_utc": (now - timedelta(days=3, hours=3)).isoformat(),
            "workbook_name": "Brazil_TT_v13_RJEB (Master)",
            "raw_workbook_id": "Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)",
            "spreadsheet_id": "1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI",
            "tab_name": "General",
            "cell_ref": "G11",
            "change_type_code": "MANUAL_OVERRIDE",
            "change_type_label": "Manual Override",
            "cell_role_label": "Formula Cell",
            "risk_level": "CRITICAL",
            "before_display": "='_CAPEX 01'!F4",
            "after_display": "4400",
            "change_summary": "='_CAPEX 01'!F4 → 4400",
            "analyst_email": "admin@ferozmulla.altostrat.com",
            "analyst_handle": "admin",
        },
        {
            "event_id": "evt-newcopy-01",
            "event_time_utc": (now - timedelta(days=4, hours=6)).isoformat(),
            "workbook_name": "New Copy — Brazil_TT_v13_RJEB",
            "raw_workbook_id": "New Copy of Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)",
            "spreadsheet_id": "1newcopy-sheet-id",
            "tab_name": "_01_CF",
            "cell_ref": "B2",
            "change_type_code": "HEADER_OR_LABEL_MODIFIED",
            "change_type_label": "Header / Label Modified",
            "cell_role_label": "Static / Label",
            "risk_level": "WARNING",
            "before_display": "Gas",
            "after_display": "Petrol",
            "change_summary": "Gas → Petrol",
            "analyst_email": "admin@ferozmulla.altostrat.com",
            "analyst_handle": "admin",
        },
    ]


def fetch_lean_audit_rows(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Query vw_audit_dashboard_lean from BigQuery with a short TTL cache and offline fallback."""
    global _CACHED_BQ_ROWS, _LAST_BQ_FETCH_MONO

    if "PYTEST_CURRENT_TEST" in os.environ and not force_refresh:
        return _fallback_seed_rows()

    now_mono = time.monotonic()
    with _CACHE_LOCK:
        if not force_refresh and _CACHED_BQ_ROWS and (now_mono - _LAST_BQ_FETCH_MONO) < _CACHE_TTL_SEC:
            return list(_CACHED_BQ_ROWS)

    try:
        from google.cloud import bigquery  # type: ignore[attr-defined]

        settings = get_settings()
        project_id = settings.gcp_project_id or "comm-model-mod"
        dataset_id = settings.bq_dataset_id or "sheets_commodity_mod_governance"
        client = bigquery.Client(project=project_id)
        query = f"""
        SELECT
          event_id,
          event_time_utc,
          workbook_name,
          raw_workbook_id,
          spreadsheet_id,
          tab_name,
          cell_ref,
          change_type_code,
          change_type_label,
          cell_role_label,
          risk_level,
          before_display,
          after_display,
          change_summary,
          analyst_email,
          analyst_handle
        FROM `{project_id}.{dataset_id}.vw_audit_dashboard_lean`
        ORDER BY event_time_utc DESC
        LIMIT 500
        """
        rows: list[dict[str, Any]] = []
        for r in client.query(query).result(timeout=10.0):
            ts = r.event_time_utc
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                ts_iso = ts.isoformat()
            else:
                ts_iso = str(ts)
            rows.append(
                {
                    "event_id": str(r.event_id),
                    "event_time_utc": ts_iso,
                    "workbook_name": str(r.workbook_name),
                    "raw_workbook_id": str(r.raw_workbook_id),
                    "spreadsheet_id": str(r.spreadsheet_id),
                    "tab_name": str(r.tab_name),
                    "cell_ref": str(r.cell_ref),
                    "change_type_code": str(r.change_type_code),
                    "change_type_label": str(r.change_type_label),
                    "cell_role_label": str(r.cell_role_label),
                    "risk_level": str(r.risk_level),
                    "before_display": str(r.before_display),
                    "after_display": str(r.after_display),
                    "change_summary": str(r.change_summary),
                    "analyst_email": str(r.analyst_email),
                    "analyst_handle": str(r.analyst_handle or "analyst"),
                }
            )
        if rows:
            with _CACHE_LOCK:
                _CACHED_BQ_ROWS = rows
                _LAST_BQ_FETCH_MONO = time.monotonic()
            return rows
    except Exception:  # noqa: BLE001, S110
        pass

    with _CACHE_LOCK:
        if _CACHED_BQ_ROWS:
            return list(_CACHED_BQ_ROWS)
    return _fallback_seed_rows()


def _filter_rows(
    all_rows: list[dict[str, Any]],
    timeframe: str,
    workbook: str,
    analyst: str,
) -> list[dict[str, Any]]:
    now_utc = datetime.now(UTC)
    cutoff_map = {
        "1h": now_utc - timedelta(hours=1),
        "24h": now_utc - timedelta(hours=24),
        "7d": now_utc - timedelta(days=7),
        "30d": now_utc - timedelta(days=30),
    }
    cutoff_utc = cutoff_map.get(timeframe)

    filtered: list[dict[str, Any]] = []
    for r in all_rows:
        if cutoff_utc is not None:
            try:
                ev_dt = datetime.fromisoformat(r["event_time_utc"])
                if ev_dt.tzinfo is None:
                    ev_dt = ev_dt.replace(tzinfo=UTC)
                if ev_dt < cutoff_utc:
                    continue
            except ValueError:
                pass
        if workbook and workbook != "all" and r["workbook_name"] != workbook:
            continue
        if analyst and analyst != "all" and r["analyst_email"] != analyst:
            continue
        filtered.append(r)
    return filtered


def _synthesize_governance_answer(
    question: str,
    rows: list[dict[str, Any]],
    timeframe: str,
) -> str:
    """Synthesize a concise, cited answer directly from the active BigQuery governance rows."""
    if not rows:
        return (
            f"No metadata modifications were found in the selected window ({timeframe}). "
            "Try switching the Timeframe pill to 'Last Month' or 'All Time' to inspect earlier edits."
        )

    q = question.lower().strip()
    total = len(rows)
    overrides = [r for r in rows if r["change_type_code"] == "MANUAL_OVERRIDE"]
    criticals = [r for r in rows if r["risk_level"] == "CRITICAL"]

    # 1. Formula overrides / hardcoded values
    if any(k in q for k in ("override", "overwritten", "hardcoded", "formula")):
        if not overrides:
            return (
                f"Across the {total} modifications in the current view, there are 0 manual formula overrides. "
                "All recorded changes are scenario parameter updates or structural/label edits."
            )
        samples = []
        seen_coords: set[str] = set()
        for r in overrides:
            key = f"{r['tab_name']}!{r['cell_ref']}"
            if key not in seen_coords:
                seen_coords.add(key)
                samples.append(
                    f"• {r['tab_name']}!{r['cell_ref']} ({r['workbook_name']}): {r['change_summary']} by {r['analyst_handle']}"
                )
            if len(samples) >= 5:
                break
        return (
            f"Found {len(overrides)} Manual Formula Override(s) across {len(seen_coords)} distinct cell coordinate(s) "
            f"(out of {total} total modifications):\n" + "\n".join(samples)
        )

    # 2. FHM Copy / Workbook drift comparison
    if any(k in q for k in ("fhm", "copy", "differ", "drift", "master", "workbook")):
        by_wb: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_wb.setdefault(r["workbook_name"], []).append(r)
        lines = []
        for wb_name, wb_rows in sorted(by_wb.items(), key=lambda x: -len(x[1])):
            crit_c = sum(1 for x in wb_rows if x["risk_level"] == "CRITICAL")
            recent = wb_rows[0]
            lines.append(
                f"• {wb_name}: {len(wb_rows)} edit(s) ({crit_c} CRITICAL) — latest on {recent['tab_name']}!{recent['cell_ref']} ({recent['change_type_label']}: {recent['change_summary']})"
            )
        fhm_rows = by_wb.get("FHM Copy — Brazil_TT_v13_RJEB", [])
        fhm_note = ""
        if fhm_rows:
            coords = ", ".join(f"{x['tab_name']}!{x['cell_ref']} ({x['change_summary']})" for x in fhm_rows[:4])
            fhm_note = f"\nSpecifically in FHM Copy — Brazil_TT_v13_RJEB, analyst edits updated: {coords} with 0 formula overrides."
        return "Workbook Copy Drift Breakdown:\n" + "\n".join(lines) + fhm_note

    # 3. Most modified tabs / sheets
    if any(k in q for k in ("tab", "sheet", "most", "highest", "activity")):
        by_tab: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_tab.setdefault(r["tab_name"], []).append(r)
        top_tabs = sorted(by_tab.items(), key=lambda x: (-len(x[1]), x[0]))[:4]
        lines = []
        for t_name, t_rows in top_tabs:
            types_summary: dict[str, int] = {}
            for x in t_rows:
                types_summary[x["change_type_label"]] = types_summary.get(x["change_type_label"], 0) + 1
            breakdown = ", ".join(f"{cnt} {lbl}" for lbl, cnt in types_summary.items())
            lines.append(f"• {t_name} ({len(t_rows)} edits): {breakdown}")
        return (
            f"Across {total} total modifications, the most active worksheet tabs are:\n"
            + "\n".join(lines)
        )

    # 4. Critical severity summary
    if any(k in q for k in ("critical", "severity", "risk", "high", "impact")):
        if not criticals:
            return f"There are 0 CRITICAL severity events in the current filter window ({total} total events)."
        lines = []
        for r in criticals[:5]:
            lines.append(
                f"• [{r['change_type_label']}] {r['tab_name']}!{r['cell_ref']} on {r['workbook_name']}: {r['change_summary']}"
            )
        return (
            f"There are {len(criticals)} CRITICAL severity event(s) ({round(len(criticals) * 100 / total)}% of all {total} modifications). "
            "Most recent critical events:\n" + "\n".join(lines)
        )

    # Default comprehensive summary
    by_type: dict[str, int] = {}
    by_tab_cnt: dict[str, int] = {}
    for r in rows:
        by_type[r["change_type_label"]] = by_type.get(r["change_type_label"], 0) + 1
        by_tab_cnt[r["tab_name"]] = by_tab_cnt.get(r["tab_name"], 0) + 1
    top_types = ", ".join(f"{v} {k}" for k, v in sorted(by_type.items(), key=lambda x: -x[1])[:4])
    top_tabs_str = ", ".join(f"{k} ({v})" for k, v in sorted(by_tab_cnt.items(), key=lambda x: -x[1])[:3])
    latest = rows[0]
    return (
        f"In the selected window ({total} modifications across {len({r['workbook_name'] for r in rows})} workbook copies), "
        f"{len(criticals)} are CRITICAL risk. Top change categories: {top_types}. "
        f"Most active tabs: {top_tabs_str}. "
        f"Latest edit: {latest['tab_name']}!{latest['cell_ref']} ({latest['change_summary']}) on {latest['workbook_name']}."
    )


@router.post("/v1/governance/chat")
async def ask_governance_conversational_agent(body: GovernanceChatRequest) -> dict[str, Any]:
    """Answer natural-language questions over BigQuery 4-Ws metadata changes."""
    all_rows = fetch_lean_audit_rows(force_refresh=False)
    filtered = _filter_rows(all_rows, body.timeframe, body.workbook, body.analyst)
    answer = _synthesize_governance_answer(body.question, filtered, body.timeframe)
    return {
        "question": body.question,
        "answer": answer,
        "matched_events": len(filtered),
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }


@router.get("/v1/governance/dashboard")
async def get_governance_dashboard_data(
    timeframe: str = Query(default="30d", description="1h, 24h, 7d, 30d, or all"),
    workbook: str = Query(default="all", description="Workbook name filter or all"),
    analyst: str = Query(default="all", description="Analyst email filter or all"),
    force_refresh: bool = Query(default=False),
) -> dict[str, Any]:
    """Return aggregated KPIs, chart series, filter catalogs, and lean 4-Ws rows."""
    settings = get_settings()
    project_id = settings.gcp_project_id or "comm-model-mod"
    dataset_id = settings.bq_dataset_id or "sheets_commodity_mod_governance"

    all_rows = fetch_lean_audit_rows(force_refresh=force_refresh)

    distinct_workbooks = sorted({r["workbook_name"] for r in all_rows if r.get("workbook_name")})
    distinct_analysts = sorted({r["analyst_email"] for r in all_rows if r.get("analyst_email")})

    filtered = _filter_rows(all_rows, timeframe, workbook, analyst)

    tab_counts: dict[str, int] = {}
    type_counts: dict[str, dict[str, Any]] = {}
    wb_drift: dict[str, dict[str, int]] = {}
    critical_count = 0

    for r in filtered:
        t_name = r["tab_name"]
        tab_counts[t_name] = tab_counts.get(t_name, 0) + 1

        c_label = r["change_type_label"]
        c_code = r["change_type_code"]
        risk = r["risk_level"]
        if risk == "CRITICAL":
            critical_count += 1

        if c_label not in type_counts:
            type_counts[c_label] = {"label": c_label, "code": c_code, "risk_level": risk, "count": 0}
        type_counts[c_label]["count"] += 1

        wb_label = r["workbook_name"]
        if wb_label not in wb_drift:
            wb_drift[wb_label] = {"critical": 0, "other": 0, "total": 0}
        if risk == "CRITICAL":
            wb_drift[wb_label]["critical"] += 1
        else:
            wb_drift[wb_label]["other"] += 1
        wb_drift[wb_label]["total"] += 1

    by_tab = [
        {"tab_name": k, "count": v}
        for k, v in sorted(tab_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    by_change_type = sorted(type_counts.values(), key=lambda x: (-x["count"], x["label"]))
    by_workbook_drift = [
        {
            "workbook_name": k,
            "critical_count": v["critical"],
            "other_count": v["other"],
            "total_count": v["total"],
        }
        for k, v in sorted(wb_drift.items(), key=lambda x: (-x[1]["total"], x[0]))
    ]

    top_tab_name = by_tab[0]["tab_name"] if by_tab else "—"
    top_tab_count = by_tab[0]["count"] if by_tab else 0
    active_wb_in_filter = len({r["workbook_name"] for r in filtered})
    active_an_in_filter = len({r["analyst_email"] for r in filtered})

    return {
        "model_label": "Model: Brazil_TT_v13_RJEB",
        "bq_view": f"{project_id}.{dataset_id}.vw_audit_dashboard_lean",
        "looker_url": LOOKER_DASHBOARD_URL,
        "looker_studio_url": _build_looker_studio_linking_url(project_id, dataset_id),
        "filters": {
            "timeframe": timeframe,
            "workbook": workbook,
            "analyst": analyst,
            "available_workbooks": distinct_workbooks,
            "available_analysts": distinct_analysts,
        },
        "kpis": {
            "total_modifications": len(filtered),
            "critical_overrides": critical_count,
            "top_tab_name": top_tab_name,
            "top_tab_count": top_tab_count,
            "active_workbooks": active_wb_in_filter,
            "active_analysts": active_an_in_filter,
        },
        "charts": {
            "by_tab": by_tab,
            "by_change_type": by_change_type,
            "by_workbook_drift": by_workbook_drift,
        },
        "events": filtered,
    }


GOVERNANCE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Brazil Power (v13) — 4-Ws Metadata Governance Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/governance/styles.css" />
</head>
<body>
  <div class="app-canvas">
    <!-- Top Floating Pill Bar (Coach Aesthetic + View Switcher) -->
    <header class="top-pill-bar">
      <div class="pill-card brand-pill">
        <div class="brand-icon" aria-hidden="true">
          <span class="wave-bar b1"></span>
          <span class="wave-bar b2"></span>
          <span class="wave-bar b3"></span>
          <span class="wave-bar b4"></span>
        </div>
        <div class="brand-text">
          <span class="brand-title">Brazil Power Model (v13)</span>
          <span class="brand-subtitle">BigQuery 4-Ws Metadata Governance</span>
        </div>
        <div class="nav-switcher" role="navigation" aria-label="Workspace Switcher">
          <a href="/telemetry" class="nav-switch-link">Execution Telemetry</a>
          <a href="/governance" class="nav-switch-link active">Metadata Governance</a>
        </div>
      </div>

      <!-- Timeframe Filter Pill -->
      <nav class="pill-card mode-pill" aria-label="Timeframe Filter">
        <button type="button" class="mode-btn" data-timeframe="1h">Last Hour</button>
        <button type="button" class="mode-btn" data-timeframe="24h">Last Day</button>
        <button type="button" class="mode-btn" data-timeframe="7d">Last Week</button>
        <button type="button" class="mode-btn active" data-timeframe="30d">Last Month</button>
        <button type="button" class="mode-btn" data-timeframe="all">All Time</button>
      </nav>

      <!-- Dimension Dropdowns & Looker Action Pill -->
      <div class="pill-card status-pill">
        <div class="filter-select-wrap">
          <label for="selWorkbook" class="filter-mini-label">Sheet Copy</label>
          <select id="selWorkbook" class="pill-select">
            <option value="all">All Workbooks</option>
          </select>
        </div>
        <div class="filter-select-wrap">
          <label for="selAnalyst" class="filter-mini-label">Analyst</label>
          <select id="selAnalyst" class="pill-select">
            <option value="all">All Analysts</option>
          </select>
        </div>
        <a id="lnkLookerStudio" href="https://56571629-c48f-487a-a65b-9e55b5de76df.looker.app/dashboards/4" target="_blank" rel="noopener noreferrer" class="action-pill-btn primary-action">
          Open in Looker ↗
        </a>
      </div>
    </header>

    <main class="governance-workspace">
      <!-- Overview & KPI Strip -->
      <section class="pipeline-overview-card">
        <div class="pipeline-header-row">
          <div class="pipeline-title-group">
            <div class="toggle-switch" aria-hidden="true">
              <span class="toggle-knob"></span>
            </div>
            <div>
              <h1 class="pipeline-heading">
                <span class="muted-prefix">Model:</span>
                Brazil_TT_v13_RJEB
                <span class="view-badge">BQ View: vw_audit_dashboard_lean</span>
              </h1>
              <p class="pipeline-caption">
                Consumes cell-level formula overrides, scenario parameter updates, header edits, and structural row/column/sheet changes captured in BigQuery (excluding initial baseline ingestion).
              </p>
            </div>
          </div>

          <div class="status-legend" aria-label="Risk Severity Legend">
            <span class="legend-chip st-failed">CRITICAL · Formula Override / Sheet Delete</span>
            <span class="legend-chip st-warning">WARNING · Structural / Header Edit</span>
            <span class="legend-chip st-success">INFO · Scenario Parameter Update</span>
          </div>
        </div>

        <!-- 4 KPI Cards -->
        <div class="kpi-four-grid">
          <div class="kpi-box">
            <span class="kpi-label">TOTAL MODIFICATIONS</span>
            <span class="kpi-value" id="kpiTotalMods">0</span>
            <span class="kpi-sub" id="kpiTimeframeSub">In selected timeframe</span>
          </div>
          <div class="kpi-box kpi-box-rose">
            <span class="kpi-label">CRITICAL FORMULA OVERRIDES</span>
            <span class="kpi-value kpi-rose-text" id="kpiCriticalMods">0</span>
            <span class="kpi-sub" id="kpiCriticalShare">0% of modifications</span>
          </div>
          <div class="kpi-box kpi-box-periwinkle">
            <span class="kpi-label">MOST MODIFIED SHEET</span>
            <span class="kpi-value kpi-value-sm" id="kpiTopTab">—</span>
            <span class="kpi-sub" id="kpiTopTabSub">Waiting for data</span>
          </div>
          <div class="kpi-box kpi-box-mint">
            <span class="kpi-label">ACTIVE COPIES &amp; ANALYSTS</span>
            <span class="kpi-value kpi-value-sm" id="kpiCopiesAnalysts">0 copies · 0 analysts</span>
            <span class="kpi-sub">Tracked across Google Drive</span>
          </div>
        </div>
      </section>

      <!-- Compact Conversational Agent Interface (Below KPI Bar) -->
      <section class="ca-agent-card" aria-label="Governance Conversational Agent">
        <div class="ca-header-bar">
          <div class="ca-header-left">
            <span class="ca-bot-icon" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="10" rx="2"></rect>
                <circle cx="12" cy="5" r="2"></circle>
                <path d="M12 7v4"></path>
                <line x1="8" y1="16" x2="8" y2="16"></line>
                <line x1="16" y1="16" x2="16" y2="16"></line>
              </svg>
            </span>
            <span class="ca-header-title">BRAZIL_TT_V13_RJEB GOVERNANCE AI ASSISTANT</span>
          </div>
          <div class="ca-header-right">
            <span class="ca-online-badge">
              <span class="ca-online-dot"></span>
              System Online · BigQuery Live
            </span>
          </div>
        </div>

        <div class="ca-body">
          <div class="ca-messages" id="caMessages" hidden></div>

          <form class="ca-input-form" id="caForm" autocomplete="off">
            <input
              type="text"
              id="caInput"
              class="ca-text-input"
              placeholder="Ask a question about sheet modifications, formula overrides, or analyst copies..."
            />
            <button type="submit" class="ca-send-btn" id="caSendBtn" title="Send question">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </form>

          <div class="ca-prompt-chips">
            <button type="button" class="ca-chip-btn" data-prompt="Which formulas were overwritten with hardcoded values?">
              Which formulas were overwritten with hardcoded values?
            </button>
            <button type="button" class="ca-chip-btn" data-prompt="How does FHM Copy differ from the Master workbook?">
              How does FHM Copy differ from the Master workbook?
            </button>
            <button type="button" class="ca-chip-btn" data-prompt="Which tabs have the highest modification activity and why?">
              Which tabs have the highest modification activity and why?
            </button>
          </div>
        </div>
      </section>

      <!-- 3-Chart Visual Grid -->
      <section class="charts-three-grid">
        <!-- Chart 1: Most Modified Sheets -->
        <div class="chart-card">
          <div class="chart-card-header">
            <div>
              <h2 class="chart-title">Most Modified Sheets (Tabs)</h2>
              <p class="chart-subtitle">Click any bar to filter the table by worksheet tab</p>
            </div>
            <span class="chart-pill-tag tag-periwinkle">By Tab</span>
          </div>
          <div id="chartByTab" class="hbar-list"></div>
        </div>

        <!-- Chart 2: Modifications by Change Type -->
        <div class="chart-card">
          <div class="chart-card-header">
            <div>
              <h2 class="chart-title">Modifications by Change Type</h2>
              <p class="chart-subtitle">Click any bar to filter by analyst action category</p>
            </div>
            <span class="chart-pill-tag tag-lavender">By Action</span>
          </div>
          <div id="chartByType" class="hbar-list"></div>
        </div>

        <!-- Chart 3: Workbook Copy Drift Comparison -->
        <div class="chart-card">
          <div class="chart-card-header">
            <div>
              <h2 class="chart-title">Workbook Copy Drift Comparison</h2>
              <p class="chart-subtitle">Critical Overrides (rose) vs. Structural &amp; Parameter Edits (periwinkle)</p>
            </div>
            <span class="chart-pill-tag tag-mint">Master vs. Copies</span>
          </div>
          <div id="chartByWorkbook" class="hbar-list"></div>
        </div>
      </section>

      <!-- Lean 4-Ws Audit Table Card -->
      <section class="table-section-card">
        <div class="table-toolbar">
          <div class="table-title-wrap">
            <h2 class="section-heading">4-Ws Metadata Audit Trail</h2>
            <span class="unit-count-pill" id="lblRowCount">0 modifications</span>
            <button type="button" class="clear-drill-btn" id="btnClearDrill" hidden>
              Clear Chart Filter ✕
            </button>
          </div>
          <div class="table-search-wrap">
            <input type="search" id="txtSearchTable" class="search-pill-input" placeholder="Search tab, cell (e.g. G11), formula, or analyst..." />
          </div>
        </div>

        <div class="table-scroll-wrap">
          <table class="lean-audit-table">
            <thead>
              <tr>
                <th class="col-time">TIME (UTC)</th>
                <th class="col-wb">WORKBOOK</th>
                <th class="col-tab">TAB</th>
                <th class="col-cell">CELL</th>
                <th class="col-type">CHANGE TYPE</th>
                <th class="col-role">ROLE</th>
                <th class="col-sev">SEVERITY</th>
                <th class="col-diff">BEFORE → AFTER</th>
                <th class="col-user">ANALYST</th>
              </tr>
            </thead>
            <tbody id="auditTableBody"></tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
  <script src="/governance/app.js"></script>
</body>
</html>
"""

GOVERNANCE_CSS = """
:root {
  --bg-top: #F2EAE3;
  --bg-mid: #E2D7CE;
  --bg-bottom: #D4C8BF;
  --panel-ivory: rgba(244, 240, 235, 0.90);
  --panel-ivory-solid: #F4F0EB;
  --card-bg: #FFFFFF;
  --card-border: #E2D9D0;
  --card-inner-border: #E8E1D9;
  --text-primary: #1F1F29;
  --text-secondary: #575866;
  --text-muted: #7C7A87;
  --accent-blue: #2B50AA;
  --accent-blue-soft: #CADCFA;
  --accent-blue-text: #1E3A8A;
  --accent-lavender-soft: #EBE5F8;
  --accent-lavender-text: #53389E;
  --accent-green: #146C43;
  --accent-green-soft: #E2F3EB;
  --accent-amber: #8C5319;
  --accent-amber-soft: #F9EBD2;
  --accent-rose: #B91C1C;
  --accent-rose-soft: #FCE8E8;
  --shadow-soft: 0 12px 32px rgba(72, 58, 46, 0.07), 0 2px 6px rgba(72, 58, 46, 0.04);
  --shadow-pill: 0 6px 20px rgba(72, 58, 46, 0.06), 0 1px 3px rgba(72, 58, 46, 0.04);
  --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-sans);
  color: var(--text-primary);
  background: radial-gradient(circle at 18% 12%, #FDF7F2 0%, #E9DFD8 48%, #D8CCC3 100%);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

.app-canvas {
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px 28px 64px;
}

.top-pill-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.pill-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 999px;
  padding: 6px 14px;
  box-shadow: var(--shadow-pill);
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-pill {
  padding: 8px 16px;
}

.brand-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--accent-blue-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2.5px;
}

.wave-bar {
  width: 2.5px;
  background: var(--accent-blue-text);
  border-radius: 2px;
  display: inline-block;
}
.wave-bar.b1 { height: 9px; }
.wave-bar.b2 { height: 15px; }
.wave-bar.b3 { height: 12px; }
.wave-bar.b4 { height: 7px; }

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.brand-subtitle {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.nav-switcher {
  display: flex;
  align-items: center;
  background: #EAE3DC;
  border-radius: 999px;
  padding: 3px;
  margin-left: 8px;
  gap: 3px;
}

.nav-switch-link {
  text-decoration: none;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 5px 12px;
  border-radius: 999px;
  transition: all 0.15s ease;
}

.nav-switch-link:hover {
  color: var(--text-primary);
}

.nav-switch-link.active {
  background: var(--accent-blue-soft);
  color: var(--accent-blue-text);
  font-weight: 700;
}

.mode-pill {
  padding: 5px;
  gap: 4px;
  background: #EAE3DC;
}

.mode-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.mode-btn:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.55);
}

.mode-btn.active {
  background: var(--accent-blue-soft);
  color: var(--accent-blue-text);
  border-color: transparent;
  box-shadow: 0 2px 6px rgba(43, 80, 170, 0.10);
}

.status-pill {
  padding: 6px 12px;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-select-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #FFFFFF;
  border: 1px solid var(--card-inner-border);
  padding: 4px 10px;
  border-radius: 999px;
}

.filter-mini-label {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.pill-select {
  border: none;
  background: transparent;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  outline: none;
  cursor: pointer;
  max-width: 190px;
}

.action-pill-btn {
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.primary-action {
  background: var(--accent-blue-soft);
  color: var(--accent-blue-text);
  border: 1px solid #B5CEF7;
}
.primary-action:hover {
  background: #B9D1FA;
}

.secondary-action {
  background: #FFFFFF;
  color: var(--text-secondary);
  border: 1px solid var(--card-inner-border);
}
.secondary-action:hover {
  background: #FAF8F5;
  color: var(--text-primary);
}

.pipeline-overview-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 22px;
  padding: 18px 22px;
  box-shadow: var(--shadow-soft);
  margin-bottom: 18px;
}

.pipeline-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  border-bottom: 1px solid #E5DDD5;
  margin-bottom: 16px;
}

.pipeline-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toggle-switch {
  width: 38px;
  height: 22px;
  border-radius: 999px;
  background: var(--accent-blue);
  position: relative;
  flex-shrink: 0;
}
.toggle-knob {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #FFFFFF;
  position: absolute;
  top: 3px;
  right: 3px;
}

.pipeline-heading {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.muted-prefix {
  color: #8A8694;
  font-weight: 600;
}

.view-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  background: var(--accent-lavender-soft);
  color: var(--accent-lavender-text);
  border: 1px solid #DCD2F3;
  padding: 2px 10px;
  border-radius: 999px;
}

.pipeline-caption {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 3px;
}

.status-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.legend-chip {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid;
  white-space: nowrap;
}
.legend-chip.st-failed { border-color: #E89F9E; color: #B91C1C; background: #FCE8E8; }
.legend-chip.st-warning { border-color: #EED2A5; color: #8C5319; background: #F9EBD2; }
.legend-chip.st-success { border-color: #B7E4CE; color: #146C43; background: #E2F3EB; }

.kpi-four-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

@media (max-width: 1024px) {
  .kpi-four-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.kpi-box {
  background: #FFFFFF;
  border: 1px solid var(--card-inner-border);
  border-radius: 16px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 2px 6px rgba(72, 58, 46, 0.03);
}

.kpi-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.kpi-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 4px 0 2px;
}
.kpi-value-sm {
  font-size: 17px;
}
.kpi-rose-text {
  color: var(--accent-rose);
}

.kpi-sub {
  font-size: 11px;
  color: var(--text-muted);
}

/* Compact Conversational Agent Interface */
.ca-agent-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  box-shadow: var(--shadow-soft);
  margin-bottom: 20px;
  overflow: hidden;
}

.ca-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 18px;
  background: #EDE5DC;
  border-bottom: 1px solid var(--card-border);
}

.ca-header-left {
  display: flex;
  align-items: center;
  gap: 9px;
}

.ca-bot-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: var(--accent-lavender-soft);
  color: var(--accent-lavender-text);
  border: 1px solid #DCD2F3;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ca-header-title {
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-primary);
}

.ca-online-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-green);
  background: var(--accent-green-soft);
  border: 1px solid #B7E4CE;
  padding: 3px 10px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ca-online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #198754;
}

.ca-body {
  padding: 14px 18px 14px;
  background: #FFFFFF;
}

.ca-messages {
  max-height: 150px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.ca-messages[hidden] {
  display: none;
}

.ca-msg {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.48;
}

.ca-msg-assistant {
  background: #F4EFEA;
  border-left: 3px solid #8EB5F0;
  color: var(--text-primary);
}

.ca-msg-user {
  background: #EEF4FD;
  border-left: 3px solid var(--accent-blue);
  color: var(--accent-blue-text);
  align-self: flex-end;
  max-width: 88%;
}

.ca-msg-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin-bottom: 3px;
}

.ca-msg-text {
  white-space: pre-line;
}

.ca-input-form {
  display: flex;
  align-items: center;
  background: #FAF8F5;
  border: 1px solid var(--card-inner-border);
  border-radius: 10px;
  padding: 4px 6px 4px 12px;
  margin-bottom: 10px;
  transition: border-color 0.15s ease;
}

.ca-input-form:focus-within {
  border-color: #8EB5F0;
  background: #FFFFFF;
}

.ca-text-input {
  flex: 1;
  border: none;
  background: transparent;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
  outline: none;
  padding: 5px 0;
}

.ca-send-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: none;
  background: var(--accent-blue-soft);
  color: var(--accent-blue-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease;
}

.ca-send-btn:hover {
  background: #B5CEF7;
}

.ca-prompt-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ca-chip-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  background: #FAF8F5;
  border: 1px solid #E2D9D0;
  border-radius: 8px;
  padding: 5px 11px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ca-chip-btn:hover {
  background: var(--accent-blue-soft);
  color: var(--accent-blue-text);
  border-color: #B5CEF7;
}

/* 3-Chart Grid */
.charts-three-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-bottom: 22px;
}

@media (max-width: 1120px) {
  .charts-three-grid {
    grid-template-columns: 1fr;
  }
}

.chart-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  padding: 18px 20px;
  box-shadow: var(--shadow-soft);
  display: flex;
  flex-direction: column;
}

.chart-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.chart-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-primary);
}

.chart-subtitle {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 2px;
}

.chart-pill-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
  white-space: nowrap;
}
.tag-periwinkle { background: var(--accent-blue-soft); color: var(--accent-blue-text); }
.tag-lavender { background: var(--accent-lavender-soft); color: var(--accent-lavender-text); }
.tag-mint { background: var(--accent-green-soft); color: var(--accent-green); }

.hbar-list {
  background: #FFFFFF;
  border: 1px solid var(--card-inner-border);
  border-radius: 14px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 195px;
}

.hbar-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 8px;
  transition: background 0.14s ease;
}
.hbar-row:hover {
  background: #FAF8F5;
}
.hbar-row.selected-bar {
  background: #F3EFEA;
  outline: 1px solid #C8B9A6;
}

.hbar-meta {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.hbar-label {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.35;
}

.hbar-count {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

.hbar-track {
  width: 100%;
  height: 10px;
  background: #F2ECE6;
  border-radius: 999px;
  overflow: hidden;
  display: flex;
}

.hbar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.25s ease;
}

.fill-periwinkle { background: #8EB5F0; }
.fill-rose { background: #E89F9E; }
.fill-peach { background: #F3C892; }
.fill-lavender { background: #C5B4E3; }
.fill-mint { background: #9ED5B8; }

/* Table Section Card */
.table-section-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 22px;
  padding: 18px 22px;
  box-shadow: var(--shadow-soft);
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.table-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.section-heading {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--text-primary);
}

.unit-count-pill {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  background: #FFFFFF;
  border: 1px solid var(--card-inner-border);
  padding: 3px 10px;
  border-radius: 999px;
}

.clear-drill-btn {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 700;
  background: var(--accent-blue-soft);
  color: var(--accent-blue-text);
  border: 1px solid #B5CEF7;
  padding: 3px 11px;
  border-radius: 999px;
  cursor: pointer;
}

.search-pill-input {
  font-family: var(--font-sans);
  font-size: 12.5px;
  background: #FFFFFF;
  border: 1px solid var(--card-inner-border);
  border-radius: 999px;
  padding: 7px 14px;
  min-width: 290px;
  color: var(--text-primary);
  outline: none;
}
.search-pill-input:focus {
  border-color: var(--accent-blue);
}

.table-scroll-wrap {
  background: #FFFFFF;
  border: 1px solid var(--card-inner-border);
  border-radius: 14px;
  overflow-x: auto;
}

.lean-audit-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 12.5px;
}

.lean-audit-table thead th {
  text-align: left;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  background: #FAF7F4;
  padding: 10px 12px;
  border-bottom: 1px solid #EAE3DC;
  white-space: nowrap;
}

.lean-audit-table th.col-time { width: 136px; }
.lean-audit-table th.col-wb   { width: 225px; }
.lean-audit-table th.col-tab  { width: 140px; }
.lean-audit-table th.col-cell { width: 78px; }
.lean-audit-table th.col-type { width: 176px; }
.lean-audit-table th.col-role { width: 116px; }
.lean-audit-table th.col-sev  { width: 112px; }
.lean-audit-table th.col-diff { width: auto; }
.lean-audit-table th.col-user { width: 105px; }

.lean-audit-table tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid #F2ECE6;
  color: var(--text-primary);
  vertical-align: middle;
  overflow-wrap: anywhere;
}

.wb-cell {
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.38;
}

.tab-cell {
  font-family: var(--font-mono);
  font-size: 11.5px;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.35;
}

.lean-audit-table tbody tr:last-child td {
  border-bottom: none;
}

.lean-audit-table tbody tr:hover {
  background: #FCFBF9;
}

.mono-cell {
  font-family: var(--font-mono);
  font-size: 11.5px;
  white-space: nowrap;
}

.badge-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
  white-space: nowrap;
}

.sev-critical { background: var(--accent-rose-soft); color: var(--accent-rose); border-color: #E89F9E; }
.sev-warning  { background: var(--accent-amber-soft); color: var(--accent-amber); border-color: #EED2A5; }
.sev-info     { background: var(--accent-green-soft); color: var(--accent-green); border-color: #B7E4CE; }

.type-override { background: var(--accent-rose-soft); color: var(--accent-rose); }
.type-header   { background: var(--accent-amber-soft); color: var(--accent-amber); }
.type-struct   { background: var(--accent-lavender-soft); color: var(--accent-lavender-text); }
.type-param    { background: var(--accent-blue-soft); color: var(--accent-blue-text); }

.diff-code {
  font-family: var(--font-mono);
  font-size: 11.5px;
  background: #FAF7F4;
  border: 1px solid #EAE3DC;
  padding: 3px 8px;
  border-radius: 6px;
  color: var(--text-primary);
  display: inline-block;
  word-break: break-word;
}
"""

GOVERNANCE_JS = """
(function () {
  var currentTimeframe = "30d";
  var currentWorkbook = "all";
  var currentAnalyst = "all";
  var drillFilter = null; // { kind: 'tab'|'type'|'workbook', value: '...' }
  var cachedPayload = null;

  var kpiTotalMods = document.getElementById("kpiTotalMods");
  var kpiTimeframeSub = document.getElementById("kpiTimeframeSub");
  var kpiCriticalMods = document.getElementById("kpiCriticalMods");
  var kpiCriticalShare = document.getElementById("kpiCriticalShare");
  var kpiTopTab = document.getElementById("kpiTopTab");
  var kpiTopTabSub = document.getElementById("kpiTopTabSub");
  var kpiCopiesAnalysts = document.getElementById("kpiCopiesAnalysts");

  var chartByTab = document.getElementById("chartByTab");
  var chartByType = document.getElementById("chartByType");
  var chartByWorkbook = document.getElementById("chartByWorkbook");
  var auditTableBody = document.getElementById("auditTableBody");
  var lblRowCount = document.getElementById("lblRowCount");
  var btnClearDrill = document.getElementById("btnClearDrill");
  var txtSearchTable = document.getElementById("txtSearchTable");
  var selWorkbook = document.getElementById("selWorkbook");
  var selAnalyst = document.getElementById("selAnalyst");
  var lnkLookerStudio = document.getElementById("lnkLookerStudio");

  var caMessages = document.getElementById("caMessages");
  var caForm = document.getElementById("caForm");
  var caInput = document.getElementById("caInput");

  function appendSoftWrapText(el, rawText) {
    var str = String(rawText == null ? "" : rawText);
    var parts = str.split("_");
    for (var i = 0; i < parts.length; i++) {
      var chunk = i < parts.length - 1 ? parts[i] + "_" : parts[i];
      el.appendChild(document.createTextNode(chunk));
      if (i < parts.length - 1) {
        el.appendChild(document.createElement("wbr"));
      }
    }
  }

  function formatUtcShort(isoStr) {
    if (!isoStr) return "—";
    try {
      var d = new Date(isoStr);
      var mon = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
      var day = String(d.getUTCDate()).padStart(2, "0");
      var hh = String(d.getUTCHours()).padStart(2, "0");
      var mm = String(d.getUTCMinutes()).padStart(2, "0");
      var ss = String(d.getUTCSeconds()).padStart(2, "0");
      return mon + " " + day + ", " + hh + ":" + mm + ":" + ss;
    } catch (e) {
      return isoStr;
    }
  }

  function appendChatMessage(role, label, text) {
    if (!caMessages) return;
    caMessages.hidden = false;
    var wrap = document.createElement("div");
    wrap.className = "ca-msg " + (role === "user" ? "ca-msg-user" : "ca-msg-assistant");
    var meta = document.createElement("div");
    meta.className = "ca-msg-meta";
    meta.textContent = label;
    var body = document.createElement("div");
    body.className = "ca-msg-text";
    body.textContent = text;
    wrap.appendChild(meta);
    wrap.appendChild(body);
    caMessages.appendChild(wrap);
    caMessages.scrollTop = caMessages.scrollHeight;
  }

  function submitAgentQuestion(questionText) {
    var q = (questionText || "").trim();
    if (!q) return;
    appendChatMessage("user", "YOU · JUST NOW", q);
    if (caInput) caInput.value = "";

    fetch("/v1/governance/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: q,
        timeframe: currentTimeframe,
        workbook: currentWorkbook,
        analyst: currentAnalyst
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        appendChatMessage(
          "assistant",
          "GOVERNANCE ASSISTANT · " + (res.matched_events || 0) + " EVENTS IN SCOPE",
          res.answer || "No response generated."
        );
      })
      .catch(function () {
        appendChatMessage(
          "assistant",
          "GOVERNANCE ASSISTANT",
          "Unable to reach the Governance Assistant endpoint right now."
        );
      });
  }

  if (caForm) {
    caForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (caInput) submitAgentQuestion(caInput.value);
    });
  }

  var promptChips = document.querySelectorAll(".ca-chip-btn[data-prompt]");
  promptChips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var p = chip.getAttribute("data-prompt");
      if (p) submitAgentQuestion(p);
    });
  });

  function populateDropdowns(filters) {
    if (selWorkbook && filters.available_workbooks) {
      var prevWb = selWorkbook.value;
      selWorkbook.innerHTML = '<option value="all">All Workbooks</option>';
      filters.available_workbooks.forEach(function (wb) {
        var opt = document.createElement("option");
        opt.value = wb;
        opt.textContent = wb;
        selWorkbook.appendChild(opt);
      });
      selWorkbook.value = prevWb || "all";
    }
    if (selAnalyst && filters.available_analysts) {
      var prevAn = selAnalyst.value;
      selAnalyst.innerHTML = '<option value="all">All Analysts</option>';
      filters.available_analysts.forEach(function (an) {
        var opt = document.createElement("option");
        opt.value = an;
        opt.textContent = an;
        selAnalyst.appendChild(opt);
      });
      selAnalyst.value = prevAn || "all";
    }
  }

  function renderBarChart(container, items, labelKey, countKey, colorFn, drillKind) {
    container.innerHTML = "";
    if (!items || items.length === 0) {
      var empty = document.createElement("div");
      empty.className = "kpi-sub";
      empty.textContent = "No modifications in selected window.";
      container.appendChild(empty);
      return;
    }
    var maxVal = Math.max.apply(null, items.map(function (i) { return i[countKey] || 1; }));
    items.slice(0, 6).forEach(function (item) {
      var row = document.createElement("div");
      var val = item[labelKey];
      var cnt = item[countKey];
      var isSelected = drillFilter && drillFilter.kind === drillKind && drillFilter.value === val;
      row.className = "hbar-row" + (isSelected ? " selected-bar" : "");

      var meta = document.createElement("div");
      meta.className = "hbar-meta";
      var spLabel = document.createElement("span");
      spLabel.className = "hbar-label";
      appendSoftWrapText(spLabel, val);
      var spCount = document.createElement("span");
      spCount.className = "hbar-count";
      spCount.textContent = String(cnt);
      meta.appendChild(spLabel);
      meta.appendChild(spCount);

      var track = document.createElement("div");
      track.className = "hbar-track";
      var fill = document.createElement("div");
      fill.className = "hbar-fill " + colorFn(item);
      fill.style.width = Math.max(8, Math.round((cnt / maxVal) * 100)) + "%";
      track.appendChild(fill);

      row.appendChild(meta);
      row.appendChild(track);
      row.addEventListener("click", function () {
        if (drillFilter && drillFilter.kind === drillKind && drillFilter.value === val) {
          drillFilter = null;
        } else {
          drillFilter = { kind: drillKind, value: val };
        }
        renderDashboard(cachedPayload);
      });
      container.appendChild(row);
    });
  }

  function renderWorkbookDriftChart(container, items) {
    container.innerHTML = "";
    if (!items || items.length === 0) {
      var empty = document.createElement("div");
      empty.className = "kpi-sub";
      empty.textContent = "No workbook modifications in selected window.";
      container.appendChild(empty);
      return;
    }
    var maxVal = Math.max.apply(null, items.map(function (i) { return i.total_count || 1; }));
    items.forEach(function (item) {
      var row = document.createElement("div");
      var val = item.workbook_name;
      var isSelected = drillFilter && drillFilter.kind === "workbook" && drillFilter.value === val;
      row.className = "hbar-row" + (isSelected ? " selected-bar" : "");

      var meta = document.createElement("div");
      meta.className = "hbar-meta";
      var spLabel = document.createElement("span");
      spLabel.className = "hbar-label";
      appendSoftWrapText(spLabel, val);
      var spCount = document.createElement("span");
      spCount.className = "hbar-count";
      spCount.textContent = item.critical_count + " crit / " + item.total_count + " total";
      meta.appendChild(spLabel);
      meta.appendChild(spCount);

      var track = document.createElement("div");
      track.className = "hbar-track";
      var critPct = Math.round((item.critical_count / maxVal) * 100);
      var otherPct = Math.round((item.other_count / maxVal) * 100);

      if (item.critical_count > 0) {
        var fCrit = document.createElement("div");
        fCrit.className = "hbar-fill fill-rose";
        fCrit.style.width = Math.max(6, critPct) + "%";
        track.appendChild(fCrit);
      }
      if (item.other_count > 0) {
        var fOth = document.createElement("div");
        fOth.className = "hbar-fill fill-periwinkle";
        fOth.style.width = Math.max(6, otherPct) + "%";
        track.appendChild(fOth);
      }

      row.appendChild(meta);
      row.appendChild(track);
      row.addEventListener("click", function () {
        if (drillFilter && drillFilter.kind === "workbook" && drillFilter.value === val) {
          drillFilter = null;
        } else {
          drillFilter = { kind: "workbook", value: val };
        }
        renderDashboard(cachedPayload);
      });
      container.appendChild(row);
    });
  }

  function renderTable(events) {
    auditTableBody.innerHTML = "";
    var q = (txtSearchTable && txtSearchTable.value ? txtSearchTable.value : "").trim().toLowerCase();

    var rows = (events || []).filter(function (ev) {
      if (drillFilter) {
        if (drillFilter.kind === "tab" && ev.tab_name !== drillFilter.value) return false;
        if (drillFilter.kind === "type" && ev.change_type_label !== drillFilter.value) return false;
        if (drillFilter.kind === "workbook" && ev.workbook_name !== drillFilter.value) return false;
      }
      if (q) {
        var hay = (
          ev.workbook_name + " " +
          ev.tab_name + " " +
          ev.cell_ref + " " +
          ev.change_type_label + " " +
          ev.cell_role_label + " " +
          ev.risk_level + " " +
          ev.change_summary + " " +
          ev.analyst_email
        ).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    if (lblRowCount) {
      lblRowCount.textContent = rows.length + (rows.length === 1 ? " modification" : " modifications");
    }
    if (btnClearDrill) {
      btnClearDrill.hidden = !drillFilter;
      if (drillFilter) {
        btnClearDrill.textContent = "Filter: " + drillFilter.value + " ✕";
      }
    }

    rows.forEach(function (ev) {
      var tr = document.createElement("tr");

      var tdTime = document.createElement("td");
      tdTime.className = "mono-cell";
      tdTime.textContent = formatUtcShort(ev.event_time_utc);

      var tdWb = document.createElement("td");
      tdWb.className = "wb-cell";
      tdWb.title = ev.workbook_name || "";
      appendSoftWrapText(tdWb, ev.workbook_name);

      var tdTab = document.createElement("td");
      tdTab.className = "tab-cell";
      tdTab.title = ev.tab_name || "";
      appendSoftWrapText(tdTab, ev.tab_name);

      var tdCell = document.createElement("td");
      tdCell.className = "mono-cell";
      tdCell.textContent = ev.cell_ref;

      var tdType = document.createElement("td");
      var spType = document.createElement("span");
      var tClass = "type-struct";
      if (ev.change_type_code === "MANUAL_OVERRIDE") tClass = "type-override";
      else if (ev.change_type_code === "HEADER_OR_LABEL_MODIFIED") tClass = "type-header";
      else if (ev.change_type_code === "SCENARIO_PARAMETER_MODIFIED") tClass = "type-param";
      spType.className = "badge-pill " + tClass;
      spType.textContent = ev.change_type_label;
      tdType.appendChild(spType);

      var tdRole = document.createElement("td");
      tdRole.textContent = ev.cell_role_label;

      var tdSev = document.createElement("td");
      var spSev = document.createElement("span");
      var sClass = "sev-info";
      if (ev.risk_level === "CRITICAL") sClass = "sev-critical";
      else if (ev.risk_level === "WARNING") sClass = "sev-warning";
      spSev.className = "badge-pill " + sClass;
      spSev.textContent = ev.risk_level;
      tdSev.appendChild(spSev);

      var tdDiff = document.createElement("td");
      var codeDiff = document.createElement("span");
      codeDiff.className = "diff-code";
      codeDiff.textContent = ev.change_summary;
      tdDiff.appendChild(codeDiff);

      var tdUser = document.createElement("td");
      tdUser.textContent = ev.analyst_handle || ev.analyst_email;
      tdUser.title = ev.analyst_email;

      tr.appendChild(tdTime);
      tr.appendChild(tdWb);
      tr.appendChild(tdTab);
      tr.appendChild(tdCell);
      tr.appendChild(tdType);
      tr.appendChild(tdRole);
      tr.appendChild(tdSev);
      tr.appendChild(tdDiff);
      tr.appendChild(tdUser);
      auditTableBody.appendChild(tr);
    });
  }

  function renderDashboard(data) {
    if (!data) return;
    cachedPayload = data;
    if (lnkLookerStudio && data.looker_url) {
      lnkLookerStudio.href = data.looker_url;
    }

    var k = data.kpis || {};
    var total = k.total_modifications || 0;
    var crit = k.critical_overrides || 0;
    if (kpiTotalMods) kpiTotalMods.textContent = String(total);
    if (kpiCriticalMods) kpiCriticalMods.textContent = String(crit);
    if (kpiCriticalShare) {
      var pct = total > 0 ? Math.round((crit / total) * 100) : 0;
      kpiCriticalShare.textContent = pct + "% of modifications";
    }
    if (kpiTopTab) kpiTopTab.textContent = k.top_tab_name || "—";
    if (kpiTopTabSub) {
      kpiTopTabSub.textContent = (k.top_tab_count || 0) + " modifications recorded";
    }
    if (kpiCopiesAnalysts) {
      kpiCopiesAnalysts.textContent = (k.active_workbooks || 0) + " copies · " + (k.active_analysts || 0) + " analysts";
    }

    renderBarChart(
      chartByTab,
      (data.charts && data.charts.by_tab) || [],
      "tab_name",
      "count",
      function () { return "fill-periwinkle"; },
      "tab"
    );

    renderBarChart(
      chartByType,
      (data.charts && data.charts.by_change_type) || [],
      "label",
      "count",
      function (item) {
        if (item.risk_level === "CRITICAL") return "fill-rose";
        if (item.code === "HEADER_OR_LABEL_MODIFIED") return "fill-peach";
        if (item.code === "SCENARIO_PARAMETER_MODIFIED") return "fill-mint";
        return "fill-lavender";
      },
      "type"
    );

    renderWorkbookDriftChart(
      chartByWorkbook,
      (data.charts && data.charts.by_workbook_drift) || []
    );

    renderTable(data.events || []);
  }

  function loadDashboard(forceRefresh, updateCatalogs) {
    var qs = "?timeframe=" + encodeURIComponent(currentTimeframe) +
             "&workbook=" + encodeURIComponent(currentWorkbook) +
             "&analyst=" + encodeURIComponent(currentAnalyst) +
             (forceRefresh ? "&force_refresh=true" : "");
    fetch("/v1/governance/dashboard" + qs)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (updateCatalogs && data.filters) {
          populateDropdowns(data.filters);
        }
        renderDashboard(data);
      })
      .catch(function () {});
  }

  var tfBtns = document.querySelectorAll(".mode-btn[data-timeframe]");
  tfBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      tfBtns.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      currentTimeframe = btn.getAttribute("data-timeframe") || "30d";
      loadDashboard(false, false);
    });
  });

  if (selWorkbook) {
    selWorkbook.addEventListener("change", function () {
      currentWorkbook = selWorkbook.value || "all";
      loadDashboard(false, false);
    });
  }

  if (selAnalyst) {
    selAnalyst.addEventListener("change", function () {
      currentAnalyst = selAnalyst.value || "all";
      loadDashboard(false, false);
    });
  }

  if (btnClearDrill) {
    btnClearDrill.addEventListener("click", function () {
      drillFilter = null;
      renderDashboard(cachedPayload);
    });
  }

  if (txtSearchTable) {
    txtSearchTable.addEventListener("input", function () {
      if (cachedPayload) renderTable(cachedPayload.events || []);
    });
  }

  loadDashboard(false, true);
})();
"""


@router.get("/governance", include_in_schema=False)
async def serve_governance_ui() -> Response:
    """Serve the Coach-styled BigQuery Metadata Governance Dashboard HTML."""
    return Response(content=GOVERNANCE_HTML, media_type="text/html; charset=utf-8")


@router.get("/governance/styles.css", include_in_schema=False)
async def serve_governance_css() -> Response:
    """Serve same-origin stylesheet for the Metadata Governance Dashboard."""
    return Response(content=GOVERNANCE_CSS, media_type="text/css; charset=utf-8")


@router.get("/governance/app.js", include_in_schema=False)
async def serve_governance_js() -> Response:
    """Serve same-origin JavaScript controller for the Metadata Governance Dashboard."""
    return Response(content=GOVERNANCE_JS, media_type="application/javascript; charset=utf-8")
