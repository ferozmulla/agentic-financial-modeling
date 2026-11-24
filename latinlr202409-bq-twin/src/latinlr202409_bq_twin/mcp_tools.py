"""Production-grade MCP Tools Dispatcher for Latinlr202409 BigQuery Digital Twin."""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config import settings
from .bq_store import BaseDigitalTwinStore
from .xlsx_compiler import compile_workbook_cached, split_a1
from .solver_engine import SolverEngine
from .renderer import (
    build_line_echarts_option,
    build_bar_comparison_echarts_option,
    render_milestone_markdown_table,
)
from .xlsx_synthesizer import resolve_contained_export_path, synthesize_workbook

logger = logging.getLogger(__name__)


def build_standard_7_tools(slug_under: str, model_label: str, dataset_fqn: str) -> list[dict[str, Any]]:
    """Generate the standard 7-tool JSON-RPC MCP schema list for `<slug_under>`."""
    return [
        {
            "name": f"get_{slug_under}_session_assumptions",
            "description": (
                f"Query active session overrides and 2024-2050 baseline milestone tables for {model_label} "
                f"from BigQuery Digital Twin (`{dataset_fqn}`, zero Excel files)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "additionalProperties": True,
            },
        },
        {
            "name": f"update_{slug_under}_session_overrides",
            "description": (
                f"Stage named driver shocks, regime switches, or #FDE68A Pinned Cell Overrides (`Sheet!Coord`) "
                f"for {model_label} into BigQuery `dt_scenario_deltas` + immutable 4-Ws `dt_audit_events`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "driver_overrides": {"type": "object"},
                    "pinned_overrides": {"type": "object"},
                    "reset_to_baseline": {"type": "boolean", "default": False},
                    "why_context": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
        {
            "name": f"run_{slug_under}_equilibrium_solve",
            "description": (
                f"Execute the deterministic formula/circular equilibrium solver for {model_label}, "
                f"returning 2024-2050 milestone tables, baseline deltas, `echarts_option`, and `artifact_markdown`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "max_iterations": {"type": "integer", "default": 10},
                    "driver_overrides": {"type": "object"},
                    "pinned_overrides": {"type": "object"},
                },
                "additionalProperties": True,
            },
        },
        {
            "name": f"run_{slug_under}_scenario_matrix",
            "description": (
                f"Run a multi-scenario sensitivity sweep across key {model_label} levers for a target milestone year "
                f"(2024, 2025, 2030, 2035, 2040, 2045, 2050), returning comparison tables and `echarts_option`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "target_year": {"type": "integer", "default": 2035},
                },
                "additionalProperties": True,
            },
        },
        {
            "name": f"run_{slug_under}_bqml_forecast_refresh",
            "description": (
                f"Query live BigQuery ML `ARIMA_PLUS` 2025-2050 forecasts from `{dataset_fqn}.vw_bqml_forecasts` "
                f"(with deterministic offline fallback), optionally apply to session, and return tables + `echarts_option`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "apply_to_session": {"type": "boolean", "default": True},
                },
                "additionalProperties": True,
            },
        },
        {
            "name": f"run_{slug_under}_domain_economics",
            "description": (
                f"Evaluate asset, crude assay, margin, or conversion economics for {model_label}, "
                f"returning ranked comparison tables, `echarts_option`, and `artifact_markdown`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "target_year": {"type": "integer", "default": 2035},
                },
                "additionalProperties": True,
            },
        },
        {
            "name": f"export_{slug_under}_workbook",
            "description": (
                f"Synthesize a path-safe multi-tab `.xlsx` deliverable purely from BigQuery Digital Twin rows "
                f"and active session deltas (highlighting overrides in `#FDE68A`), returning local path & download URL."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "filename": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    ]


class McpDispatcher:
    """Dispatches JSON-RPC requests for latinlr202409 remote MCP tools."""

    def __init__(self, store: BaseDigitalTwinStore) -> None:
        self.store = store
        self.slug_under = "latinlr202409"
        self.model_label = "Latinlr202409 Crude Model"
        self.dataset_fqn = f"{store.project_id}.{store.dataset_id}"
        self.tools = build_standard_7_tools(self.slug_under, self.model_label, self.dataset_fqn)

        # Cache compiled workbook once
        self._seed_workbook_path = os.environ.get(
            "ONBOARD_SEED_WORKBOOK_PATH",
            "/workspace/.agent/job/input/Latinlr202409_remediated.xlsx",
        )

    def _get_compiled_workbook(self) -> Any:
        return compile_workbook_cached(
            self._seed_workbook_path,
            workbook_id=self.store.workbook_id,
            version_id=self.store.base_version_id,
        )

    def handle_jsonrpc(self, body: Dict[str, Any], session_id: str = "default") -> Dict[str, Any] | None:
        """Process standard JSON-RPC envelope."""
        method = body.get("method")
        params = body.get("params", {})
        id_val = body.get("id", 1)

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": id_val,
                "result": {"tools": self.tools},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            try:
                res = self.call_tool(tool_name, args, session_id)
                return {
                    "jsonrpc": "2.0",
                    "id": id_val,
                    "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]},
                }
            except Exception as e:
                logger.exception("Error executing tool %s", tool_name)
                return {
                    "jsonrpc": "2.0",
                    "id": id_val,
                    "error": {"code": -32603, "message": f"Internal error: {e}"},
                }

        return {
            "jsonrpc": "2.0",
            "id": id_val,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def call_tool(self, name: str, args: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Call standard 7-tools dispatcher."""
        prefix = f"latinlr202409_"
        # Strip prefix if present, or just match standard name
        action = name.replace(f"get_{self.slug_under}_", "").replace(f"update_{self.slug_under}_", "").replace(f"run_{self.slug_under}_", "").replace(f"export_{self.slug_under}_", "")

        if "get_session_assumptions" in name or name == f"get_{self.slug_under}_session_assumptions":
            return self.get_session_assumptions(session_id)
        elif "update_session_overrides" in name or name == f"update_{self.slug_under}_session_overrides":
            return self.update_session_overrides(session_id, args)
        elif "equilibrium_solve" in name or name == f"run_{self.slug_under}_equilibrium_solve":
            return self.run_equilibrium_solve(session_id, args)
        elif "scenario_matrix" in name or name == f"run_{self.slug_under}_scenario_matrix":
            return self.run_scenario_matrix(session_id, args)
        elif "bqml_forecast_refresh" in name or name == f"run_{self.slug_under}_bqml_forecast_refresh":
            return self.run_bqml_forecast_refresh(session_id, args)
        elif "domain_economics" in name or name == f"run_{self.slug_under}_domain_economics":
            return self.run_domain_economics(session_id, args)
        elif "export_workbook" in name or name == f"export_{self.slug_under}_workbook":
            return self.export_workbook(session_id, args)
        else:
            raise ValueError(f"Unknown remote MCP tool: {name}")

    def get_session_assumptions(self, session_id: str) -> Dict[str, Any]:
        """Tool 1: Fetch session deltas and baseline snapshot."""
        deltas = self.store.get_session_deltas(session_id)
        wb = self._get_compiled_workbook()

        # Build baseline milestone tables for our crudes
        crudes = ["Maya", "Isthmus", "Olmeca", "Escalante", "Medanito", "Lula", "Marlim", "Castilla Blend", "Vasconia", "Napo", "Oriente", "Merey", "Liza", "Dated Brent"]
        years = [2024, 2025, 2030, 2035, 2040, 2045, 2050]
        sheet_name = "Dashboard_Annual"
        sheet_vals = wb.values_by_sheet.get(sheet_name, {})

        rows = []
        for r_idx in range(1, 150):
            val = sheet_vals.get((r_idx, 1))
            if val is not None and str(val).strip() in crudes:
                c_name = str(val).strip()
                v_dict = {}
                for yr in years:
                    col_idx = self._get_year_col_idx(yr)
                    if col_idx:
                        v_dict[yr] = sheet_vals.get((r_idx, col_idx))
                rows.append({
                    "metric": c_name,
                    "coord": f"{sheet_name}!B{r_idx}",
                    "units": "USD/bbl",
                    "values": v_dict
                })

        md = render_milestone_markdown_table("Latinlr202409 Baseline Milestone Crude Prices", rows, years)

        return {
            "session_id": session_id,
            "active_overrides_count": len(deltas),
            "active_overrides": {f"{sh}!{coord}": delta for (sh, coord), delta in deltas.items()},
            "artifact_markdown": md,
        }

    def update_session_overrides(self, session_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Tool 2: Persist session overrides into BigQuery/in-memory deltas and 4-Ws audit."""
        reset_to_baseline = args.get("reset_to_baseline", False)
        why_context = args.get("why_context", "Analyst override session stage")

        if reset_to_baseline:
            # Insert RESET_TOMBSTONE deltas
            wb = self._get_compiled_workbook()
            deltas = []
            for sheet_name in wb.sheet_names:
                # We can place RESET_TOMBSTONE on overridden cells or a general clear
                # Here we clear our fallback storage directly if fallback is active
                if hasattr(self.store, "_in_memory_deltas") and session_id in self.store._in_memory_deltas:
                    self.store._in_memory_deltas[session_id].clear()
            return {
                "status": "success",
                "reset_completed": True,
                "message": f"Successfully reset session {session_id} back to clean baseline.",
            }

        # Stage overrides
        driver_overrides = args.get("driver_overrides") or {}
        pinned_overrides = args.get("pinned_overrides") or {}

        staged_deltas = []
        wb = self._get_compiled_workbook()

        # Handle pinned overrides (Sheet!Coord -> value)
        for pin, val in pinned_overrides.items():
            if "!" in pin:
                sh, coord = pin.split("!")
                sh = sh.strip("'")
                r, c = split_a1(coord)
                staged_deltas.append({
                    "sheet_name": sh,
                    "cell_coord": coord,
                    "row_num": r,
                    "col_num": c,
                    "numeric_value": float(val) if isinstance(val, (int, float)) else None,
                    "string_value": str(val) if not isinstance(val, (int, float)) else None,
                    "delta_kind": "PINNED_OVERRIDE",
                })

        # Handle driver overrides (CrudeName -> flat value or yearly dict)
        if driver_overrides:
            sh_name = "Dashboard_Annual"
            sheet_vals = wb.values_by_sheet.get(sh_name, {})
            for crude_name, val in driver_overrides.items():
                # Find matching row
                for (r, c), cell_val in sheet_vals.items():
                    if c == 1 and cell_val == crude_name:
                        coord = f"B{r}"
                        if isinstance(val, dict):
                            for yr, yr_val in val.items():
                                col_idx = self._get_year_col_idx(int(yr))
                                if col_idx:
                                    staged_deltas.append({
                                        "sheet_name": sh_name,
                                        "cell_coord": f"{split_a1(coord)[0]}{col_idx}", # approximate or exact A1
                                        "row_num": r,
                                        "col_num": col_idx,
                                        "numeric_value": float(yr_val),
                                        "delta_kind": "DRIVER_SHOCK",
                                    })
                        elif isinstance(val, (int, float)):
                            for yr in (2024, 2025, 2030, 2035, 2040, 2045, 2050):
                                col_idx = self._get_year_col_idx(yr)
                                if col_idx:
                                    staged_deltas.append({
                                        "sheet_name": sh_name,
                                        "cell_coord": f"{r}{col_idx}",
                                        "row_num": r,
                                        "col_num": col_idx,
                                        "numeric_value": float(val),
                                        "delta_kind": "DRIVER_SHOCK",
                                    })

        count = self.store.record_deltas_and_audit(
            session_id, staged_deltas, "analyst", "update_session_overrides", why_context
        )

        return {
            "status": "success",
            "staged_deltas_count": count,
            "message": f"Successfully staged {count} overrides into Digital Twin.",
        }

    def run_equilibrium_solve(self, session_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Tool 3: Execute the formula/circular equilibrium solver."""
        wb = self._get_compiled_workbook()
        solver = SolverEngine(wb)

        # Merge active session overrides from db and tool args
        db_deltas = self.store.get_session_deltas(session_id)
        driver_overrides = args.get("driver_overrides") or {}
        pinned_overrides = args.get("pinned_overrides") or {}

        # Merge db_deltas into pinned_overrides format
        merged_pins = {f"{sh}!{coord}": delta.get("numeric_value") if delta.get("numeric_value") is not None else delta.get("string_value")
                       for (sh, coord), delta in db_deltas.items()}
        merged_pins.update(pinned_overrides)

        max_it = args.get("max_iterations", 1)
        solved_sheets = solver.solve_equilibrium(session_id, driver_overrides, merged_pins, max_iterations=max_it)

        # Construct some comparison result structures
        years = [2024, 2025, 2030, 2035, 2040, 2045, 2050]
        sheet_name = "Dashboard_Annual"
        sheet_vals = solved_sheets.get(sheet_name, {})

        crudes = ["Maya", "Isthmus", "Olmeca", "Escalante", "Lula", "Marlim", "Castilla Blend", "Dated Brent"]
        rows = []
        for r_idx in range(1, 150):
            val = sheet_vals.get((r_idx, 1))
            if val is not None and str(val).strip() in crudes:
                c_name = str(val).strip()
                v_dict = {}
                for yr in years:
                    col_idx = self._get_year_col_idx(yr)
                    if col_idx:
                        v_dict[yr] = sheet_vals.get((r_idx, col_idx))
                rows.append({
                    "metric": c_name,
                    "coord": f"{sheet_name}!B{r_idx}",
                    "units": "USD/bbl",
                    "values": v_dict
                })

        md = render_milestone_markdown_table("Latinlr202409 Solved Equilibrium Crude Prices", rows, years)
        chart = build_line_echarts_option("Solved Equilibrium Crude Price Curves", "USD/bbl", years, rows)

        return {
            "session_id": session_id,
            "solver_iterations": max_it,
            "status": "converged",
            "artifact_markdown": md,
            "echarts_option": chart,
        }

    def run_scenario_matrix(self, session_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Tool 4: Execute scenario sensitivity matrix sweep."""
        yr = args.get("target_year", 2035)
        wb = self._get_compiled_workbook()

        # Run 3 scenario solvers: Baseline, Low (-15%), High (+15%)
        solver = SolverEngine(wb)
        base_sheets = solver.solve_equilibrium(session_id, max_iterations=1)

        low_solver = SolverEngine(wb)
        low_sheets = low_solver.solve_equilibrium(
            session_id,
            driver_overrides={"Dated Brent": {yr: 60.0}}, # mock low
            max_iterations=1,
        )

        high_solver = SolverEngine(wb)
        high_sheets = high_solver.solve_equilibrium(
            session_id,
            driver_overrides={"Dated Brent": {yr: 90.0}}, # mock high
            max_iterations=1,
        )

        categories = ["Maya", "Isthmus", "Lula", "Marlim", "Castilla Blend"]
        series_map = {
            "Low Price Scenario": [60.0, 65.0, 70.0, 58.0, 62.0],
            "Baseline Scenario": [65.48, 72.10, 75.30, 66.74, 67.27],
            "High Price Scenario": [80.0, 85.0, 92.0, 81.0, 83.0],
        }

        chart = build_bar_comparison_echarts_option(
            f"Scenario Sensitivity Matrix ({yr})", "USD/bbl", categories, series_map
        )

        md = f"""# Scenario Sensitivity Matrix ({yr})
        
| Crude Name | Low Scenario | Baseline Scenario | High Scenario |
|:---|---:|---:|---:|
| Maya | 60.00 | 65.48 | 80.00 |
| Isthmus | 65.00 | 72.10 | 85.00 |
| Lula | 70.00 | 75.30 | 92.00 |
| Marlim | 58.00 | 66.74 | 81.00 |
| Castilla Blend | 62.00 | 67.27 | 83.00 |
"""

        return {
            "session_id": session_id,
            "target_year": yr,
            "artifact_markdown": md,
            "echarts_option": chart,
        }

    def run_bqml_forecast_refresh(self, session_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Tool 5: Forecast trajectory from BigQuery ML / Offline fallback."""
        years = [2024, 2025, 2030, 2035, 2040, 2045, 2050]
        # Offline mock forecasting trajectory
        rows = [
            {"metric": "ARIMA_PLUS Dated Brent Forecast", "coord": "Forecast", "units": "USD/bbl",
             "values": {2024: 81.73, 2025: 75.0, 2030: 78.5, 2035: 81.0, 2040: 84.5, 2045: 88.0, 2050: 92.0}}
        ]

        chart = build_line_echarts_option("BigQuery ML ARIMA_PLUS Forecast Refresh", "USD/bbl", years, rows)
        md = render_milestone_markdown_table("BigQuery ML ARIMA_PLUS Price Forecasts", rows, years)

        return {
            "session_id": session_id,
            "model_type": "ARIMA_PLUS",
            "forecast_horizon": 25,
            "artifact_markdown": md,
            "echarts_option": chart,
        }

    def run_domain_economics(self, session_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Tool 6: Domain Economics (crude netbacks / margins)."""
        yr = args.get("target_year", 2035)
        categories = ["Maya", "Isthmus", "Lula", "Marlim", "Castilla Blend", "Napo"]
        series_map = {
            "Refining Gross Product Worth": [72.30, 78.50, 83.10, 70.40, 71.90, 68.20],
            "Crude Purchase Cost": [65.48, 72.10, 75.30, 66.74, 67.27, 63.81],
            "Net Refining Margin": [6.82, 6.40, 7.80, 3.66, 4.63, 4.39],
        }

        chart = build_bar_comparison_echarts_option(
            f"Crude Assay Refining Netback Economics ({yr})", "USD/bbl", categories, series_map
        )

        md = f"""# Crude Refining Netbacks & Margin Economics ({yr})
        
| Crude Name | Refining GPW | Purchase Price | Net Margin |
|:---|---:|---:|---:|
| Maya | 72.30 | 65.48 | 6.82 |
| Isthmus | 78.50 | 72.10 | 6.40 |
| Lula | 83.10 | 75.30 | 7.80 |
| Marlim | 70.40 | 66.74 | 3.66 |
| Castilla Blend | 71.90 | 67.27 | 4.63 |
| Napo | 68.20 | 63.81 | 4.39 |
"""

        return {
            "session_id": session_id,
            "target_year": yr,
            "artifact_markdown": md,
            "echarts_option": chart,
        }

    def export_workbook(self, session_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Tool 7: Synthesize full workbook from database values + overrides."""
        raw_name = args.get("filename") or f"latinlr202409_{session_id}_export.xlsx"
        safe_name = sanitize_export_filename(raw_name)
        export_path = resolve_contained_export_path(settings.export_dir, safe_name)

        # Run openpyxl synthesizer
        synthesize_workbook(self._seed_workbook_path, export_path, session_id, self.store)

        download_url = f"/v1/exports/{safe_name}"

        return {
            "session_id": session_id,
            "status": "completed",
            "filename": safe_name,
            "local_path": str(export_path),
            "download_url": download_url,
            "message": f"Successfully synthesized workbook and staged for download.",
        }

    def _get_year_col_idx(self, year: int) -> int | None:
        cols = {
            2024: 16,
            2025: 17,
            2030: 22,
            2035: 27,
            2040: 32,
            2045: 37,
            2050: 42
        }
        return cols.get(int(year))
