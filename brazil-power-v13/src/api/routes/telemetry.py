"""FastAPI routes and self-contained UI for the Brazil Power Cloud Execution Telemetry Web App."""

from __future__ import annotations

import copy
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from src.schemas.solver import GeneralOverrides, SolveMacroRequest
from src.schemas.telemetry import TelemetryFeedResponse
from src.solver.macros.registry import MacroExecutionRegistry
from src.solver.workbook_context import get_baseline_solver_context
from src.telemetry.tracker import telemetry_tracker

router = APIRouter(tags=["telemetry"])


class BQMLRefreshReportBody(BaseModel):
    """Payload posted by Apps Script refreshBqmlForecasts() or Connected Sheets hook."""

    workbook_id: str = Field(default="Brazil_TT_v13_RJEB_Gcloud")
    spreadsheet_id: str = Field(default="1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI")
    caller_google_user: str = Field(default="admin@ferozmulla.altostrat.com")
    active_tab: str = Field(default="LT_Capex_BQML / LT_Fuel_BQML / LT_CF_BQML")
    view_type: str = Field(default="lt_forecasts")
    duration_ms: float = Field(default=320.0)
    job_id: str | None = None


@router.get("/v1/telemetry/units", response_model=TelemetryFeedResponse)
async def get_telemetry_units(
    unit_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> TelemetryFeedResponse:
    """Return grouped Units of Execution and step trails for the near-real-time Telemetry Web App."""
    return telemetry_tracker.list_units(unit_type=unit_type, status=status)


@router.post("/v1/telemetry/bqml-refresh", response_model=TelemetryFeedResponse)
async def report_bqml_refresh(body: BQMLRefreshReportBody) -> TelemetryFeedResponse:
    """Record a Connected Sheets BigQuery ML refresh triggered from Google Sheets Apps Script."""
    now_utc = datetime.now(UTC)
    dur_ms = max(float(body.duration_ms), 25.0)
    start_utc = now_utc - timedelta(milliseconds=dur_ms)
    jid = body.job_id or f"sheets_dataconnector_gas_{int(now_utc.timestamp() * 1000)}"
    telemetry_tracker.record_connected_sheets_bqml_refresh(
        job_id=jid,
        user_email=body.caller_google_user,
        started_at_utc=start_utc,
        completed_at_utc=now_utc,
        duration_ms=dur_ms,
        trigger_source="apps-script",
        view_type=body.view_type,
        workbook_id=body.workbook_id,
        spreadsheet_id=body.spreadsheet_id,
        active_tab=body.active_tab,
    )
    return telemetry_tracker.list_units()


@router.post("/v1/telemetry/clear", response_model=TelemetryFeedResponse)
async def clear_telemetry_units() -> TelemetryFeedResponse:
    """Clear the in-memory execution telemetry trail."""
    telemetry_tracker.clear()
    return telemetry_tracker.list_units()


@router.post("/v1/telemetry/demo-seed", response_model=TelemetryFeedResponse)
async def seed_manager_demo_walkthrough() -> TelemetryFeedResponse:
    """
    Replay the exact Manager Demo Script through the real quantitative solver:
    1. Edit Utility Solar PV Base Capital Cost (General!G11) & Fuel Cost (General!G20) on General tab
    2. Click 'Tornado 5' (calcule_tir5) -> updates _05_CF!E6:G12 & Tornado tab
    3. Click 'Forecast LCOE' (lcoe_exec) -> updates 23-year forecast table Output3!B8:N30
    """
    base_ctx = get_baseline_solver_context()
    spreadsheet_id = "1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI"
    workbook_name = "Brazil_TT_v13_RJEB_Gcloud"

    # Reset the demo sheet's snapshot to the Golden Copy baseline so Unit #1 diffs against the Golden baseline
    # and Unit #2 diffs against the snapshot at the end of Unit #1
    telemetry_tracker._last_general_by_sheet[spreadsheet_id] = copy.deepcopy(base_ctx.general_c5_n40)

    modified_general = copy.deepcopy(base_ctx.general_c5_n40)
    # Row 11 -> index 6 (11 - 5), Col G -> index 4 (Utility Solar PV Base Capital Cost R$/kW)
    if len(modified_general) > 6 and len(modified_general[6]) > 4:
        old_capex = modified_general[6][4]
        modified_general[6][4] = round(float(old_capex) * 0.90, 2) if isinstance(old_capex, (int, float)) else 3850.0
    # Row 20 -> index 15 (20 - 5), Col G -> index 4 (Fuel Cost)
    if len(modified_general) > 15 and len(modified_general[15]) > 4:
        modified_general[15][4] = 12.5

    overrides = GeneralOverrides(
        general_c5_n40=modified_general,
        lt_capex_b8_j30=copy.deepcopy(base_ctx.lt_capex_b8_j30),
        lt_fuel_b8_j30=copy.deepcopy(base_ctx.lt_fuel_b8_j30),
        lt_cf_b8_j30=copy.deepcopy(base_ctx.lt_cf_b8_j30),
    )

    # Unit 1: Tornado 5 (calcule_tir5)
    t0 = time.perf_counter()
    req_tornado5 = SolveMacroRequest(
        macro_name="calcule_tir5",
        workbook_id=workbook_name,
        spreadsheet_id=spreadsheet_id,
        caller_google_user="ferozmulla@google.com",
        general_overrides=overrides,
    )
    resp_tornado5 = MacroExecutionRegistry.execute(req_tornado5)
    gw_ms_1 = round((time.perf_counter() - t0) * 1000.0, 2)
    telemetry_tracker.record_macro_solve(req_tornado5, resp_tornado5, gateway_overhead_ms=max(gw_ms_1, 2.4))

    # Unit 2: Forecast LCOE (lcoe_exec)
    t1 = time.perf_counter()
    req_lcoe = SolveMacroRequest(
        macro_name="lcoe_exec",
        workbook_id=workbook_name,
        spreadsheet_id=spreadsheet_id,
        caller_google_user="ferozmulla@google.com",
        general_overrides=overrides,
    )
    resp_lcoe = MacroExecutionRegistry.execute(req_lcoe)
    gw_ms_2 = round((time.perf_counter() - t1) * 1000.0, 2)
    telemetry_tracker.record_macro_solve(req_lcoe, resp_lcoe, gateway_overhead_ms=max(gw_ms_2, 3.1))

    return telemetry_tracker.list_units()


TELEMETRY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Brazil Power (v13) — Cloud Execution Telemetry</title>
  <link rel="stylesheet" href="/telemetry/styles.css" />
</head>
<body>
  <div class="app-canvas">
    <!-- Top Floating Pill Bar (Voice Agent App Aesthetic) -->
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
          <span class="brand-subtitle">Cloud Solver &amp; BQML Execution Telemetry</span>
        </div>
        <div class="nav-switcher" role="navigation" aria-label="Workspace Switcher">
          <a href="/telemetry" class="nav-switch-link active">Execution Telemetry</a>
          <a href="/governance" class="nav-switch-link">Metadata Governance</a>
        </div>
      </div>

      <nav class="pill-card mode-pill" aria-label="Execution Category Filter">
        <button type="button" class="mode-btn active" data-filter-group="all">All Executions</button>
        <button type="button" class="mode-btn" data-filter-group="tornado">Tornado 1–12</button>
        <button type="button" class="mode-btn" data-filter-group="lcoe">Forecast LCOE</button>
        <button type="button" class="mode-btn" data-filter-group="cvu_matrix">CVU &amp; 2D Matrices</button>
        <button type="button" class="mode-btn" data-filter-group="bqml">BQML Refresh</button>
      </nav>

      <div class="pill-card status-pill">
        <div class="live-badge" id="liveIndicator">
          <span class="live-dot"></span>
          <span class="live-label">Live</span>
        </div>
        <span class="poll-clock" id="pollTimer">00:00</span>
        <div class="signal-bars" aria-hidden="true">
          <span></span><span></span><span></span>
        </div>
        <div class="user-chip">
          <span class="user-avatar">FM</span>
          <span class="user-name">ferozmulla</span>
        </div>
        <button type="button" class="action-pill-btn danger-action" id="btnClearTrail">
          Clear Trail
        </button>
      </div>
    </header>

    <!-- Main Content Container -->
    <main class="telemetry-workspace">
      <!-- Airflow-Inspired Pipeline Control & Duration Strip -->
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
              </h1>
              <p class="pipeline-caption">
                Tracks cloud-backed Google Sheets macro runs (Tornado IRR, Forecast LCOE, CVU sweeps, 1D/2D matrices) and BQML refreshes. In-sheet-only formulas and structural metadata edits are excluded.
              </p>
            </div>
          </div>

          <div class="status-legend" aria-label="Execution Status Legend">
            <span class="legend-chip st-queued">queued</span>
            <span class="legend-chip st-running">running</span>
            <span class="legend-chip st-success">success</span>
            <span class="legend-chip st-failed">failed</span>
            <span class="legend-chip st-skipped">skipped</span>
          </div>
        </div>

        <div class="overview-split-grid">
          <!-- Left: KPI Summary Cards -->
          <div class="kpi-summary-grid">
            <div class="kpi-box">
              <span class="kpi-label">EXECUTION UNITS</span>
              <span class="kpi-value" id="kpiTotalUnits">0</span>
              <span class="kpi-sub">Grouped end-to-end runs</span>
            </div>
            <div class="kpi-box">
              <span class="kpi-label">LATEST RUN</span>
              <span class="kpi-value kpi-value-sm" id="kpiLatestMacro">—</span>
              <span class="kpi-sub" id="kpiLatestTarget">Waiting for execution</span>
            </div>
            <div class="kpi-box">
              <span class="kpi-label">AVG UNIT DURATION</span>
              <span class="kpi-value" id="kpiAvgDuration">0 ms</span>
              <span class="kpi-sub">Sheet → Cloud Run → Sheet</span>
            </div>
            <div class="kpi-box">
              <span class="kpi-label">TOTAL SOLVES</span>
              <span class="kpi-value" id="kpiTotalSolves">0</span>
              <span class="kpi-sub">Binary search &amp; DCF evaluations</span>
            </div>
          </div>

          <!-- Right: Airflow-Inspired Run Duration Bar Chart -->
          <div class="duration-chart-panel">
            <div class="chart-panel-header">
              <span class="chart-title">Unit Execution Duration (ms) — Recent Runs</span>
              <span class="chart-hint">Click any bar to jump to that Execution Unit</span>
            </div>
            <div class="duration-bars-container" id="durationChart"></div>
          </div>
        </div>
      </section>

      <!-- Grouped Units of Execution Trail -->
      <section class="units-trail-section" aria-label="Units of Execution Trail">
        <div id="unitsContainer" class="units-list"></div>
      </section>
    </main>
  </div>
  <script src="/telemetry/app.js"></script>
</body>
</html>
"""


TELEMETRY_CSS = """
:root {
  --bg-cream-top: #F2EAE3;
  --bg-cream-mid: #E2D7CE;
  --bg-cream-bottom: #D4C8BF;
  --panel-ivory: rgba(244, 240, 235, 0.90);
  --panel-ivory-header: rgba(241, 236, 230, 0.92);
  --pill-ivory: rgba(248, 245, 242, 0.93);
  --card-white: #FFFFFF;
  --card-border: rgba(255, 255, 255, 0.85);
  --inner-border: #E8E1D9;
  --row-border: #F3EFEA;
  --text-primary: #262A3A;
  --text-secondary: #4E5263;
  --text-muted: #767480;
  --accent-blue: #2B50AA;
  --accent-blue-soft: #CADCFA;
  --accent-blue-dark: #1E3A8A;
  --accent-lavender-bg: #EBE5F8;
  --accent-lavender-text: #53389E;
  --status-success: #146C43;
  --status-success-bg: #E2F3EB;
  --status-running: #1E3A8A;
  --status-running-bg: #DAE5FA;
  --status-failed: #B91C1C;
  --status-failed-bg: #FCE8E8;
  --status-queued: #575866;
  --status-queued-bg: #F1EFEA;
  --shadow-soft: 0 12px 32px rgba(62, 50, 40, 0.08);
  --shadow-pill: 0 6px 20px rgba(62, 50, 40, 0.07);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: #DFD4CC;
  background-image:
    radial-gradient(ellipse 70% 52% at 50% 8%, rgba(253, 247, 242, 0.94) 0%, rgba(238, 227, 218, 0.58) 48%, rgba(212, 201, 193, 0) 100%),
    radial-gradient(ellipse 55% 60% at 14% 45%, rgba(225, 212, 203, 0.78) 0%, rgba(196, 186, 179, 0) 100%),
    radial-gradient(ellipse 58% 60% at 86% 60%, rgba(235, 223, 214, 0.75) 0%, rgba(204, 195, 189, 0) 100%),
    linear-gradient(165deg, var(--bg-cream-top) 0%, var(--bg-cream-mid) 46%, var(--bg-cream-bottom) 78%, #E7E0DA 100%);
  background-attachment: fixed;
  color: var(--text-primary);
  min-height: 100vh;
  padding: 18px 24px 48px;
}

.app-canvas {
  max-width: 1440px;
  margin: 0 auto;
}

/* Top Floating Pill Header (Coach App Style) */
.top-pill-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.pill-card {
  background: var(--pill-ivory);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid var(--card-border);
  border-radius: 999px;
  padding: 8px 16px;
  box-shadow: var(--shadow-pill);
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-pill {
  padding: 8px 18px 8px 10px;
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
  width: 3px;
  background: var(--accent-blue);
  border-radius: 2px;
  display: inline-block;
}
.wave-bar.b1 { height: 9px; }
.wave-bar.b2 { height: 16px; }
.wave-bar.b3 { height: 12px; }
.wave-bar.b4 { height: 7px; }

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.brand-subtitle {
  font-size: 11px;
  color: var(--text-muted);
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
  color: var(--accent-blue-dark);
  font-weight: 700;
}

.mode-pill {
  padding: 5px 7px;
  gap: 4px;
}

.mode-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.mode-btn:hover {
  color: var(--text-primary);
  background: rgba(202, 220, 250, 0.38);
}

.mode-btn.active {
  background: var(--accent-blue-soft);
  color: var(--accent-blue-dark);
  border-color: transparent;
  box-shadow: 0 2px 6px rgba(43, 80, 170, 0.10);
}

.status-pill {
  padding: 6px 12px;
  gap: 12px;
}

.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--status-success-bg);
  color: var(--status-success);
  font-size: 12px;
  font-weight: 700;
  padding: 5px 11px;
  border-radius: 999px;
}

.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16A34A;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.18);
  animation: pulseDot 1.8s infinite;
}

@keyframes pulseDot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.92); }
}

.poll-clock {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.signal-bars {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 14px;
}
.signal-bars span {
  width: 3px;
  background: #16A34A;
  border-radius: 1.5px;
}
.signal-bars span:nth-child(1) { height: 6px; }
.signal-bars span:nth-child(2) { height: 10px; }
.signal-bars span:nth-child(3) { height: 14px; }

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding-left: 4px;
}

.user-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-blue);
  color: #FFFFFF;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.user-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
}

.action-pill-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.primary-action {
  background: var(--accent-blue-soft);
  color: var(--accent-blue-dark);
  border: 1px solid #B5CEF7;
}
.primary-action:hover {
  background: #B8D0F8;
}

.danger-action {
  background: #FFFDFD;
  color: #C53030;
  border: 1px solid #E89F9E;
}
.danger-action:hover {
  background: #FDF2F2;
}

/* Pipeline Overview Card (Frosted Warm Ivory Container + Crisp White Inner Cards) */
.pipeline-overview-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 22px;
  padding: 18px 22px;
  box-shadow: var(--shadow-soft);
  margin-bottom: 20px;
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
}
.muted-prefix {
  color: #8A8694;
  font-weight: 600;
  margin-right: 4px;
}

.pipeline-caption {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
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
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid;
}
.legend-chip.st-queued { border-color: #D5CFC7; color: #575866; background: #FAF8F5; }
.legend-chip.st-running { border-color: #B5CEF7; color: #1E3A8A; background: #DAE5FA; }
.legend-chip.st-success { border-color: #B7E4CE; color: #146C43; background: #E2F3EB; }
.legend-chip.st-failed { border-color: #E89F9E; color: #B91C1C; background: #FCE8E8; }
.legend-chip.st-skipped { border-color: #DCD2F3; color: #53389E; background: #EBE5F8; }

.overview-split-grid {
  display: grid;
  grid-template-columns: 1.05fr 1.35fr;
  gap: 18px;
  align-items: stretch;
}

@media (max-width: 1024px) {
  .overview-split-grid {
    grid-template-columns: 1fr;
  }
}

.kpi-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.kpi-box {
  background: var(--card-white);
  border: 1px solid var(--inner-border);
  border-radius: 15px;
  padding: 12px 15px;
  box-shadow: 0 2px 8px rgba(62, 50, 40, 0.03);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.kpi-label {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.kpi-value {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 4px 0 2px;
}

.kpi-value-sm {
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-sub {
  font-size: 11px;
  color: var(--text-muted);
}

/* Airflow-Inspired Duration Bar Chart on Crisp White Inner Surface */
.duration-chart-panel {
  background: var(--card-white);
  border: 1px solid var(--inner-border);
  border-radius: 15px;
  padding: 12px 16px;
  box-shadow: 0 2px 8px rgba(62, 50, 40, 0.03);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.chart-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.chart-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
}

.chart-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.duration-bars-container {
  height: 92px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-bottom: 1px solid #E5DDD5;
  overflow-x: auto;
}

.bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  min-width: 34px;
  cursor: pointer;
}

.bar-ms-label {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9.5px;
  color: var(--text-muted);
  margin-bottom: 3px;
}

.bar-fill {
  width: 18px;
  border-radius: 4px 4px 0 0;
  background: #1B7A4E;
  transition: transform 0.15s ease, opacity 0.15s ease;
}
.bar-col:hover .bar-fill {
  opacity: 0.85;
  transform: scaleX(1.12);
}

.bar-seq-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* Units of Execution List */
.units-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.unit-card {
  background: var(--panel-ivory);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  box-shadow: var(--shadow-soft);
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.unit-card.highlight-flash {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 3px rgba(43, 80, 170, 0.20);
}

.unit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 13px 20px;
  background: var(--panel-ivory-header);
  border-bottom: 1px solid #E5DDD5;
}

.unit-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.unit-seq-badge {
  background: var(--accent-blue);
  color: #FFFFFF;
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
}

.unit-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-primary);
}

.unit-meta-pill {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--card-white);
  border: 1px solid #DFD7CE;
  padding: 2px 10px;
  border-radius: 999px;
}

.unit-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.unit-timestamp {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11.5px;
  color: var(--text-muted);
}

.unit-duration-badge {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-blue-dark);
  background: var(--accent-blue-soft);
  border: 1px solid #B5CEF7;
  padding: 3px 11px;
  border-radius: 999px;
}

.status-badge {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid;
}
.status-badge.st-success {
  background: var(--status-success-bg);
  color: var(--status-success);
  border-color: #B7E4CE;
}
.status-badge.st-running {
  background: var(--status-running-bg);
  color: var(--status-running);
  border-color: #B5CEF7;
}
.status-badge.st-failed {
  background: var(--status-failed-bg);
  color: var(--status-failed);
  border-color: #E89F9E;
}

/* Airflow-Inspired Step Table Inside Each Execution Unit */
.step-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12.5px;
  background: var(--card-white);
}

.step-table th {
  text-align: left;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  padding: 9px 14px;
  background: #FAF8F5;
  border-bottom: 1px solid #EAE3DC;
}

.step-table td {
  padding: 9px 14px;
  border-bottom: 1px solid var(--row-border);
  vertical-align: middle;
}

.step-table th:nth-child(1), .step-table td:nth-child(1) { width: 54px; }
.step-table th:nth-child(2), .step-table td:nth-child(2) { width: 118px; }
.step-table th:nth-child(3), .step-table td:nth-child(3) { width: 17%; }
.step-table th:nth-child(4), .step-table td:nth-child(4) { width: 18%; }
.step-table th:nth-child(6), .step-table td:nth-child(6) { width: 215px; }
.step-table th:nth-child(7), .step-table td:nth-child(7) { width: 124px; }

.step-table tr:last-child td {
  border-bottom: none;
}

.step-table tr:hover td {
  background: #FAF6F2;
}

.step-idx-cell {
  width: 54px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-weight: 700;
  color: var(--text-muted);
}

.sys-pill {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 999px;
  white-space: nowrap;
}
.sys-sheets { background: #E2F3EB; color: #146C43; }
.sys-gas    { background: #F9EBD2; color: #8C5319; }
.sys-cloud  { background: #DAE5FA; color: #1E3A8A; }
.sys-solver { background: var(--accent-lavender-bg); color: var(--accent-lavender-text); }
.sys-bq     { background: #E3EFFB; color: #155E75; }

.artifact-cell {
  color: var(--text-secondary);
  font-weight: 500;
  overflow-wrap: break-word;
  word-break: break-word;
}

.component-cell {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  overflow-wrap: break-word;
  word-break: break-word;
}

.action-cell {
  color: var(--text-primary);
  font-weight: 500;
  overflow-wrap: break-word;
  word-break: break-word;
}

.timing-cell {
  white-space: nowrap;
  text-align: right;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11.5px;
  color: var(--text-secondary);
}

.Squares-cell {
  white-space: nowrap;
  width: 124px;
}

.airflow-squares {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.af-sq {
  width: 11px;
  height: 11px;
  border-radius: 2.5px;
  background: #E8E1D9;
  display: inline-block;
}
.af-sq.done {
  background: #1B7A4E;
}
.af-sq.active {
  background: #16A34A;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.25);
}

.empty-state {
  background: var(--panel-ivory);
  border: 1px dashed #CFC6BC;
  border-radius: 20px;
  padding: 42px 24px;
  text-align: center;
  color: var(--text-secondary);
}
.empty-state h3 {
  font-size: 16px;
  margin-bottom: 6px;
  color: var(--text-primary);
}
.empty-state p {
  font-size: 13px;
  color: var(--text-muted);
}
"""


TELEMETRY_JS = """
(function () {
  var activeFilter = "all";
  var latestSeqSeen = -1;
  var secondsElapsed = 0;

  var unitsContainer = document.getElementById("unitsContainer");
  var durationChart = document.getElementById("durationChart");
  var kpiTotalUnits = document.getElementById("kpiTotalUnits");
  var kpiLatestMacro = document.getElementById("kpiLatestMacro");
  var kpiLatestTarget = document.getElementById("kpiLatestTarget");
  var kpiAvgDuration = document.getElementById("kpiAvgDuration");
  var kpiTotalSolves = document.getElementById("kpiTotalSolves");
  var pollTimer = document.getElementById("pollTimer");

  function formatClock(sec) {
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return (m < 10 ? "0" + m : String(m)) + ":" + (s < 10 ? "0" + s : String(s));
  }

  setInterval(function () {
    secondsElapsed += 1;
    if (pollTimer) {
      pollTimer.textContent = formatClock(secondsElapsed);
    }
  }, 1000);

  function formatUtcTime(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      return d.toISOString().substring(11, 23) + " UTC";
    } catch (e) {
      return isoStr;
    }
  }

  function systemBadgeClass(sysName) {
    if (sysName === "Google Sheets") return "sys-pill sys-sheets";
    if (sysName === "Apps Script") return "sys-pill sys-gas";
    if (sysName === "Cloud Run") return "sys-pill sys-cloud";
    if (sysName === "Solver Engine") return "sys-pill sys-solver";
    if (sysName === "BigQuery") return "sys-pill sys-bq";
    return "sys-pill sys-cloud";
  }

  function matchesGroupFilter(unit, group) {
    if (!group || group === "all") return true;
    var m = unit.macro_name || "";
    if (group === "tornado") return m.indexOf("calcule_tir") === 0;
    if (group === "lcoe") return m === "lcoe_exec" || m === "lcoe_forecast" || m === "fator_i";
    if (group === "cvu_matrix") return m.indexOf("calculo_") === 0;
    if (group === "bqml") return unit.unit_type === "bqml_refresh";
    return true;
  }

  function renderDurationChart(units) {
    while (durationChart.firstChild) {
      durationChart.removeChild(durationChart.firstChild);
    }
    if (!units || units.length === 0) {
      var emptyMsg = document.createElement("div");
      emptyMsg.className = "chart-hint";
      emptyMsg.textContent = "No execution runs recorded yet.";
      durationChart.appendChild(emptyMsg);
      return;
    }

    var slice = units.slice(0, 18).reverse();
    var maxMs = 10;
    for (var i = 0; i < slice.length; i++) {
      if (slice[i].total_duration_ms > maxMs) {
        maxMs = slice[i].total_duration_ms;
      }
    }

    slice.forEach(function (u) {
      var col = document.createElement("div");
      col.className = "bar-col";
      col.title = "#" + u.unit_seq + " " + u.display_title + " (" + u.total_duration_ms + " ms)";

      var msLbl = document.createElement("span");
      msLbl.className = "bar-ms-label";
      msLbl.textContent = Math.round(u.total_duration_ms) + "ms";

      var fill = document.createElement("div");
      fill.className = "bar-fill";
      var hPct = Math.max(14, Math.round((u.total_duration_ms / maxMs) * 54));
      fill.style.height = hPct + "px";
      if (u.status === "failed") {
        fill.style.background = "#DC2626";
      }

      var seqLbl = document.createElement("span");
      seqLbl.className = "bar-seq-label";
      seqLbl.textContent = "#" + u.unit_seq;

      col.appendChild(msLbl);
      col.appendChild(fill);
      col.appendChild(seqLbl);

      col.addEventListener("click", function () {
        var cardEl = document.getElementById("unit-card-" + u.unit_seq);
        if (cardEl) {
          cardEl.scrollIntoView({ behavior: "smooth", block: "center" });
          cardEl.classList.add("highlight-flash");
          setTimeout(function () {
            cardEl.classList.remove("highlight-flash");
          }, 1600);
        }
      });

      durationChart.appendChild(col);
    });
  }

  function renderUnits(allUnits) {
    var filtered = allUnits.filter(function (u) {
      return matchesGroupFilter(u, activeFilter);
    });

    kpiTotalUnits.textContent = String(filtered.length);
    var totalSolves = 0;
    var sumMs = 0;
    filtered.forEach(function (u) {
      totalSolves += u.solve_count || 0;
      sumMs += u.total_duration_ms || 0;
    });
    kpiTotalSolves.textContent = String(totalSolves);
    kpiAvgDuration.textContent = filtered.length > 0
      ? (sumMs / filtered.length).toFixed(1) + " ms"
      : "0 ms";

    if (filtered.length > 0) {
      kpiLatestMacro.textContent = filtered[0].button_label + " (#" + filtered[0].unit_seq + ")";
      kpiLatestTarget.textContent = (filtered[0].target_ranges || []).join(", ") || "Completed";
    } else {
      kpiLatestMacro.textContent = "—";
      kpiLatestTarget.textContent = "Waiting for execution";
    }

    renderDurationChart(filtered);

    while (unitsContainer.firstChild) {
      unitsContainer.removeChild(unitsContainer.firstChild);
    }

    if (filtered.length === 0) {
      var emptyBox = document.createElement("div");
      emptyBox.className = "empty-state";
      var h3 = document.createElement("h3");
      h3.textContent = "Waiting for Cloud Solver or BQML Execution";
      var p = document.createElement("p");
      p.textContent = "Click a macro button on the General tab (e.g., Tornado 5 or Forecast LCOE) in the Brazil Power Google Sheet, or click 'Replay Demo Script' in the top bar.";
      emptyBox.appendChild(h3);
      emptyBox.appendChild(p);
      unitsContainer.appendChild(emptyBox);
      return;
    }

    filtered.forEach(function (unit) {
      var card = document.createElement("article");
      card.className = "unit-card";
      card.id = "unit-card-" + unit.unit_seq;

      var header = document.createElement("div");
      header.className = "unit-header";

      var hLeft = document.createElement("div");
      hLeft.className = "unit-header-left";

      var seqBadge = document.createElement("span");
      seqBadge.className = "unit-seq-badge";
      seqBadge.textContent = "Unit #" + unit.unit_seq;

      var titleSpan = document.createElement("span");
      titleSpan.className = "unit-title";
      titleSpan.textContent = unit.display_title;

      var solvesPill = document.createElement("span");
      solvesPill.className = "unit-meta-pill";
      solvesPill.textContent = unit.solve_count + " solves · " + unit.steps.length + " steps";

      hLeft.appendChild(seqBadge);
      hLeft.appendChild(titleSpan);
      hLeft.appendChild(solvesPill);

      if (unit.target_ranges && unit.target_ranges.length > 0) {
        var targetPill = document.createElement("span");
        targetPill.className = "unit-meta-pill";
        targetPill.textContent = "Target: " + unit.target_ranges.join(", ");
        hLeft.appendChild(targetPill);
      }

      var hRight = document.createElement("div");
      hRight.className = "unit-header-right";

      var tsSpan = document.createElement("span");
      tsSpan.className = "unit-timestamp";
      tsSpan.textContent = formatUtcTime(unit.started_at_utc) + " → " + formatUtcTime(unit.completed_at_utc);

      var durBadge = document.createElement("span");
      durBadge.className = "unit-duration-badge";
      durBadge.textContent = "Duration: " + unit.total_duration_ms.toFixed(1) + " ms";

      var stBadge = document.createElement("span");
      stBadge.className = "status-badge st-" + (unit.status || "success");
      stBadge.textContent = unit.status || "success";

      hRight.appendChild(tsSpan);
      hRight.appendChild(durBadge);
      hRight.appendChild(stBadge);

      header.appendChild(hLeft);
      header.appendChild(hRight);
      card.appendChild(header);

      // Step Table
      var tbl = document.createElement("table");
      tbl.className = "step-table";

      var thead = document.createElement("thead");
      var hRow = document.createElement("tr");
      ["Step", "System", "Artifact", "Component", "Specific Action", "Timestamp & Duration", "Stage Trail"].forEach(function (lbl, idx) {
        var th = document.createElement("th");
        th.textContent = lbl;
        if (idx === 5) th.style.textAlign = "right";
        hRow.appendChild(th);
      });
      thead.appendChild(hRow);
      tbl.appendChild(thead);

      var tbody = document.createElement("tbody");
      var totalSteps = unit.steps.length;

      unit.steps.forEach(function (st) {
        var tr = document.createElement("tr");

        var tdIdx = document.createElement("td");
        tdIdx.className = "step-idx-cell";
        tdIdx.textContent = "#" + st.step_index;

        var tdSys = document.createElement("td");
        var sysSpan = document.createElement("span");
        sysSpan.className = systemBadgeClass(st.system);
        sysSpan.textContent = st.system;
        tdSys.appendChild(sysSpan);

        var tdArt = document.createElement("td");
        tdArt.className = "artifact-cell";
        tdArt.textContent = st.artifact;

        var tdComp = document.createElement("td");
        tdComp.className = "component-cell";
        tdComp.textContent = st.component;

        var tdAct = document.createElement("td");
        tdAct.className = "action-cell";
        tdAct.textContent = st.action;

        var tdTime = document.createElement("td");
        tdTime.className = "timing-cell";
        tdTime.textContent = formatUtcTime(st.completed_at_utc) + "  (" + st.duration_ms.toFixed(1) + " ms)";

        var tdSq = document.createElement("td");
        tdSq.className = "Squares-cell";
        var sqWrap = document.createElement("div");
        sqWrap.className = "airflow-squares";
        for (var k = 1; k <= totalSteps; k++) {
          var sq = document.createElement("span");
          if (k < st.step_index) {
            sq.className = "af-sq done";
          } else if (k === st.step_index) {
            sq.className = "af-sq active";
          } else {
            sq.className = "af-sq";
          }
          sqWrap.appendChild(sq);
        }
        tdSq.appendChild(sqWrap);

        tr.appendChild(tdIdx);
        tr.appendChild(tdSys);
        tr.appendChild(tdArt);
        tr.appendChild(tdComp);
        tr.appendChild(tdAct);
        tr.appendChild(tdTime);
        tr.appendChild(tdSq);
        tbody.appendChild(tr);
      });

      tbl.appendChild(tbody);
      card.appendChild(tbl);
      unitsContainer.appendChild(card);
    });
  }

  var cachedUnits = [];

  function fetchUnits(forceRender) {
    fetch("/v1/telemetry/units")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        cachedUnits = data.units || [];
        if (forceRender || data.latest_unit_seq !== latestSeqSeen) {
          latestSeqSeen = data.latest_unit_seq;
          renderUnits(cachedUnits);
        }
      })
      .catch(function () {});
  }

  // Filter buttons
  var modeBtns = document.querySelectorAll(".mode-btn");
  modeBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      modeBtns.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      activeFilter = btn.getAttribute("data-filter-group") || "all";
      renderUnits(cachedUnits);
    });
  });

  // Replay Demo Script button
  var btnReplay = document.getElementById("btnReplayDemo");
  if (btnReplay) {
    btnReplay.addEventListener("click", function () {
      btnReplay.disabled = true;
      fetch("/v1/telemetry/demo-seed", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          cachedUnits = data.units || [];
          latestSeqSeen = data.latest_unit_seq;
          renderUnits(cachedUnits);
        })
        .finally(function () {
          btnReplay.disabled = false;
        });
    });
  }

  // Clear Trail button
  var btnClear = document.getElementById("btnClearTrail");
  if (btnClear) {
    btnClear.addEventListener("click", function () {
      fetch("/v1/telemetry/clear", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          cachedUnits = data.units || [];
          latestSeqSeen = data.latest_unit_seq;
          renderUnits(cachedUnits);
        });
    });
  }

  fetchUnits(true);
  setInterval(function () {
    fetchUnits(false);
  }, 1000);
})();
"""


@router.get("/telemetry", include_in_schema=False)
async def serve_telemetry_ui() -> Response:
    """Serve the near-real-time Cloud Execution Telemetry Web App HTML."""
    return Response(content=TELEMETRY_HTML, media_type="text/html; charset=utf-8")


@router.get("/telemetry/styles.css", include_in_schema=False)
async def serve_telemetry_css() -> Response:
    """Serve same-origin stylesheet for the Telemetry Web App."""
    return Response(content=TELEMETRY_CSS, media_type="text/css; charset=utf-8")


@router.get("/telemetry/app.js", include_in_schema=False)
async def serve_telemetry_js() -> Response:
    """Serve same-origin JavaScript controller for the Telemetry Web App."""
    return Response(content=TELEMETRY_JS, media_type="application/javascript; charset=utf-8")
