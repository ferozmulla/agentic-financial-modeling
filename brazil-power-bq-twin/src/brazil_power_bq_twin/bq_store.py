"""BigQuery-backed and In-Memory Digital Twin stores with parameterized queries and cost caps."""

from __future__ import annotations

import copy
import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from google.cloud import bigquery

from brazil_power_bq_twin.config import TwinSettings, get_twin_settings
from brazil_power_bq_twin.models import (
    AuditRow,
    BaselineTwinSnapshot,
    CellDelta,
    CellRecord,
    SessionOverlay,
    StyleRecord,
    WorksheetRecord,
    col_letter_to_index,
    index_to_col_letter,
    split_a1_coord,
)

logger = logging.getLogger(__name__)


def resolve_effective_cell_value(
    snapshot: BaselineTwinSnapshot,
    overlay: SessionOverlay,
    sheet_name: str,
    coord: str,
) -> Any:
    """Resolve `COALESCE(session_delta, baseline_cell)` for a single sheet coordinate."""
    delta = overlay.get_delta(sheet_name, coord)
    if delta is not None:
        return delta.value
    base_cell = snapshot.get_cell(sheet_name, coord)
    if base_cell is not None:
        return base_cell.effective_baseline_value
    return None


def resolve_effective_grid(
    snapshot: BaselineTwinSnapshot,
    overlay: SessionOverlay,
    sheet_name: str,
    start_coord: str,
    end_coord: str,
) -> list[list[Any]]:
    """Resolve a 2D rectangular cell range ('C5'..'N40') combining baseline and active session deltas."""
    c1_str, r1 = split_a1_coord(start_coord)
    c2_str, r2 = split_a1_coord(end_coord)
    c1, c2 = col_letter_to_index(c1_str), col_letter_to_index(c2_str)

    rows_out: list[list[Any]] = []
    for row_num in range(r1, r2 + 1):
        row_vals: list[Any] = []
        for col_idx in range(c1, c2 + 1):
            coord = f"{index_to_col_letter(col_idx)}{row_num}"
            row_vals.append(resolve_effective_cell_value(snapshot, overlay, sheet_name, coord))
        rows_out.append(row_vals)
    return rows_out


class DigitalTwinStore(Protocol):
    """Uniform storage interface for BigQuery and unit-test Digital Twin stores."""

    def get_baseline_snapshot(self, version_id: str = "v13_baseline") -> BaselineTwinSnapshot: ...

    def get_session_overlay(self, session_id: str, version_id: str = "v13_baseline") -> SessionOverlay: ...

    def append_session_deltas(
        self,
        session_id: str,
        deltas: list[CellDelta],
        audit_rows: list[AuditRow] | None = None,
        version_id: str = "v13_baseline",
    ) -> None: ...

    def reset_session(self, session_id: str, version_id: str = "v13_baseline") -> None: ...

    def fetch_bqml_trajectories(self) -> dict[str, Any]: ...


class InMemoryDigitalTwinStore:
    """Deterministic in-memory Digital Twin store for fast offline unit testing."""

    def __init__(
        self,
        snapshot: BaselineTwinSnapshot,
        lt_trajectories: dict[str, Any] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._sessions: dict[tuple[str, str], SessionOverlay] = {}
        self.audit_log: list[AuditRow] = []
        self._lt_trajectories = lt_trajectories or {}

    def get_baseline_snapshot(self, version_id: str = "v13_baseline") -> BaselineTwinSnapshot:
        return self._snapshot

    def get_session_overlay(self, session_id: str, version_id: str = "v13_baseline") -> SessionOverlay:
        key = (session_id, version_id)
        if key not in self._sessions:
            self._sessions[key] = SessionOverlay(
                session_id=session_id,
                workbook_id=self._snapshot.workbook_id,
                base_version_id=version_id,
            )
        return copy.deepcopy(self._sessions[key])

    def append_session_deltas(
        self,
        session_id: str,
        deltas: list[CellDelta],
        audit_rows: list[AuditRow] | None = None,
        version_id: str = "v13_baseline",
    ) -> None:
        key = (session_id, version_id)
        overlay = self._sessions.setdefault(
            key,
            SessionOverlay(
                session_id=session_id,
                workbook_id=self._snapshot.workbook_id,
                base_version_id=version_id,
            ),
        )
        for delta in deltas:
            clean_coord = delta.cell_coord.replace("$", "").strip().upper()
            overlay.deltas_by_sheet.setdefault(delta.sheet_name, {})[clean_coord] = delta
        if audit_rows:
            self.audit_log.extend(audit_rows)

    def reset_session(self, session_id: str, version_id: str = "v13_baseline") -> None:
        key = (session_id, version_id)
        existing = self._sessions.get(key)
        if not existing:
            return
        tombstones: list[CellDelta] = []
        now_iso = datetime.now(UTC).isoformat()
        for sheet_name, cmap in existing.deltas_by_sheet.items():
            for coord, delta in cmap.items():
                tombstones.append(
                    CellDelta(
                        sheet_name=sheet_name,
                        cell_coord=coord,
                        row_num=delta.row_num,
                        col_num=delta.col_num,
                        delta_kind="RESET_TOMBSTONE",
                        source_tool="reset_session",
                        updated_at=now_iso,
                    )
                )
        self.append_session_deltas(session_id, tombstones, version_id=version_id)

    def fetch_bqml_trajectories(self) -> dict[str, Any]:
        return copy.deepcopy(self._lt_trajectories)


class BigQueryDigitalTwinStore:
    """Production Digital Twin store backed by `comm-model-mod.brazil_power_digital_twin`."""

    def __init__(
        self,
        settings: TwinSettings | None = None,
        bq_client: Any | None = None,
    ) -> None:
        self.settings = settings or get_twin_settings()
        self._client = bq_client
        self._baseline_cache: dict[str, BaselineTwinSnapshot] = {}
        self._session_cache: dict[tuple[str, str], SessionOverlay] = {}

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = bigquery.Client(
                project=self.settings.gcp_project_id,
                location=self.settings.bq_location,
            )
        return self._client

    def _fq_table(self, table_name: str) -> str:
        return f"{self.settings.gcp_project_id}.{self.settings.bq_dataset}.{table_name}"

    def _run_query(self, sql: str, params: list[bigquery.ScalarQueryParameter]) -> list[Any]:
        job_cfg = bigquery.QueryJobConfig(
            query_parameters=params,
            maximum_bytes_billed=self.settings.max_bytes_billed,
            labels={"datacloud": "antigravity", "component": "bq_digital_twin"},
        )
        return list(self.client.query(sql, job_config=job_cfg).result())

    def get_baseline_snapshot(self, version_id: str = "v13_baseline") -> BaselineTwinSnapshot:
        if version_id in self._baseline_cache:
            return self._baseline_cache[version_id]

        params = [
            bigquery.ScalarQueryParameter("workbook_id", "STRING", self.settings.workbook_id),
            bigquery.ScalarQueryParameter("version_id", "STRING", version_id),
        ]
        fq_ver = f"`{self._fq_table('dt_workbook_versions')}`"
        fq_ws = f"`{self._fq_table('dt_worksheets')}`"
        fq_st = f"`{self._fq_table('dt_styles')}`"
        fq_cells = f"`{self._fq_table('dt_cells')}`"

        ver_rows = self._run_query(
            f"SELECT workbook_id, version_id, version_label, named_ranges_json, solver_parameters_json "
            f"FROM {fq_ver} WHERE workbook_id = @workbook_id AND version_id = @version_id LIMIT 1",
            params,
        )
        if not ver_rows:
            raise LookupError(
                f"Digital Twin version '{version_id}' not found in {self._fq_table('dt_workbook_versions')}."
            )
        ver = ver_rows[0]

        ws_rows = self._run_query(
            f"SELECT sheet_index, sheet_name, visibility, tab_color_rgb, merged_ranges_json, "
            f"col_widths_json, row_heights_json, freeze_panes_coord, sheet_view_json "
            f"FROM {fq_ws} WHERE workbook_id = @workbook_id AND version_id = @version_id "
            f"ORDER BY sheet_index ASC",
            params,
        )
        worksheets = [
            WorksheetRecord(
                sheet_index=int(r["sheet_index"]),
                sheet_name=str(r["sheet_name"]),
                visibility=str(r["visibility"]),
                tab_color_rgb=r["tab_color_rgb"],
                merged_ranges=tuple(json.loads(r["merged_ranges_json"] or "[]")),
                col_widths={str(k): float(v) for k, v in json.loads(r["col_widths_json"] or "{}").items()},
                row_heights={str(k): float(v) for k, v in json.loads(r["row_heights_json"] or "{}").items()},
                freeze_panes_coord=r["freeze_panes_coord"],
                sheet_view=json.loads((r.get("sheet_view_json") if isinstance(r, dict) else r["sheet_view_json"]) or "{}"),
            )
            for r in ws_rows
        ]

        st_rows = self._run_query(
            f"SELECT style_id, number_format, font_json, fill_json, border_json, alignment_json "
            f"FROM {fq_st} WHERE workbook_id = @workbook_id AND version_id = @version_id",
            params,
        )
        styles = {
            int(r["style_id"]): StyleRecord(
                style_id=int(r["style_id"]),
                number_format=str(r["number_format"] or "General"),
                font=json.loads(r["font_json"] or "{}"),
                fill=json.loads(r["fill_json"] or "{}"),
                border=json.loads(r["border_json"] or "{}"),
                alignment=json.loads(r["alignment_json"] or "{}"),
            )
            for r in st_rows
        }

        cell_rows = self._run_query(
            f"SELECT sheet_name, cell_coord, row_num, col_num, data_type, numeric_value, "
            f"string_value, raw_formula, style_id, semantic_role "
            f"FROM {fq_cells} WHERE workbook_id = @workbook_id AND version_id = @version_id",
            params,
        )
        cells_by_sheet: dict[str, dict[str, CellRecord]] = {}
        for r in cell_rows:
            sname = str(r["sheet_name"])
            coord = str(r["cell_coord"]).upper()
            cells_by_sheet.setdefault(sname, {})[coord] = CellRecord(
                sheet_name=sname,
                cell_coord=coord,
                row_num=int(r["row_num"]),
                col_num=int(r["col_num"]),
                data_type=str(r["data_type"]),
                numeric_value=float(r["numeric_value"]) if r["numeric_value"] is not None else None,
                string_value=r["string_value"],
                raw_formula=r["raw_formula"],
                style_id=int(r["style_id"]),
                semantic_role=str(r["semantic_role"]),
            )

        snapshot = BaselineTwinSnapshot(
            workbook_id=str(ver["workbook_id"]),
            version_id=str(ver["version_id"]),
            version_label=str(ver["version_label"]),
            worksheets=worksheets,
            styles=styles,
            cells_by_sheet=cells_by_sheet,
            named_ranges=json.loads(ver["named_ranges_json"] or "[]"),
            solver_parameters=json.loads(ver["solver_parameters_json"] or "{}"),
        )
        self._baseline_cache[version_id] = snapshot
        return snapshot

    def get_session_overlay(self, session_id: str, version_id: str = "v13_baseline") -> SessionOverlay:
        key = (session_id, version_id)
        if key in self._session_cache:
            return copy.deepcopy(self._session_cache[key])

        fq_view = f"`{self._fq_table('vw_dt_latest_session_deltas')}`"
        params = [
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("workbook_id", "STRING", self.settings.workbook_id),
            bigquery.ScalarQueryParameter("version_id", "STRING", version_id),
        ]
        rows = self._run_query(
            f"SELECT sheet_name, cell_coord, row_num, col_num, delta_kind, numeric_value, "
            f"string_value, source_tool, CAST(updated_at AS STRING) AS updated_at_str "
            f"FROM {fq_view} "
            f"WHERE session_id = @session_id AND workbook_id = @workbook_id AND base_version_id = @version_id",
            params,
        )
        overlay = SessionOverlay(
            session_id=session_id,
            workbook_id=self.settings.workbook_id,
            base_version_id=version_id,
        )
        for r in rows:
            sname = str(r["sheet_name"])
            coord = str(r["cell_coord"]).upper()
            overlay.deltas_by_sheet.setdefault(sname, {})[coord] = CellDelta(
                sheet_name=sname,
                cell_coord=coord,
                row_num=int(r["row_num"]),
                col_num=int(r["col_num"]),
                delta_kind=str(r["delta_kind"]),
                numeric_value=float(r["numeric_value"]) if r["numeric_value"] is not None else None,
                string_value=r["string_value"],
                source_tool=str(r["source_tool"]),
                updated_at=str(r["updated_at_str"]),
            )
        self._session_cache[key] = overlay
        return copy.deepcopy(overlay)

    def append_session_deltas(
        self,
        session_id: str,
        deltas: list[CellDelta],
        audit_rows: list[AuditRow] | None = None,
        version_id: str = "v13_baseline",
    ) -> None:
        if not deltas and not audit_rows:
            return
        key = (session_id, version_id)
        if key not in self._session_cache:
            self._session_cache[key] = SessionOverlay(
                session_id=session_id,
                workbook_id=self.settings.workbook_id,
                base_version_id=version_id,
            )
        cached_overlay = self._session_cache[key]

        bq_delta_rows: list[dict[str, Any]] = []
        for d in deltas:
            clean_coord = d.cell_coord.replace("$", "").strip().upper()
            cached_overlay.deltas_by_sheet.setdefault(d.sheet_name, {})[clean_coord] = d
            bq_delta_rows.append(
                {
                    "session_id": session_id,
                    "workbook_id": self.settings.workbook_id,
                    "base_version_id": version_id,
                    "sheet_name": d.sheet_name,
                    "cell_coord": clean_coord,
                    "row_num": d.row_num,
                    "col_num": d.col_num,
                    "delta_kind": d.delta_kind,
                    "numeric_value": d.numeric_value,
                    "string_value": d.string_value,
                    "source_tool": d.source_tool,
                    "updated_at": d.updated_at,
                }
            )
        if bq_delta_rows:
            errs = self.client.insert_rows_json(self._fq_table("dt_scenario_deltas"), bq_delta_rows)
            if errs:
                logger.warning("BigQuery insert_rows_json warnings on dt_scenario_deltas: %s", errs)

        if audit_rows:
            bq_audit = [
                {
                    "event_id": a.event_id,
                    "session_id": a.session_id,
                    "what_sheet": a.what_sheet,
                    "what_coord": a.what_coord,
                    "what_change_type": a.what_change_type,
                    "before_value": a.before_value,
                    "after_value": a.after_value,
                    "who_principal": a.who_principal,
                    "when_event_utc": a.when_event_utc,
                    "why_context": a.why_context,
                }
                for a in audit_rows
            ]
            errs = self.client.insert_rows_json(self._fq_table("dt_audit_events"), bq_audit)
            if errs:
                logger.warning("BigQuery insert_rows_json warnings on dt_audit_events: %s", errs)

    def reset_session(self, session_id: str, version_id: str = "v13_baseline") -> None:
        overlay = self.get_session_overlay(session_id, version_id=version_id)
        now_iso = datetime.now(UTC).isoformat()
        tombstones = [
            CellDelta(
                sheet_name=sname,
                cell_coord=coord,
                row_num=d.row_num,
                col_num=d.col_num,
                delta_kind="RESET_TOMBSTONE",
                source_tool="reset_session",
                updated_at=now_iso,
            )
            for sname, cmap in overlay.deltas_by_sheet.items()
            for coord, d in cmap.items()
        ]
        if tombstones:
            self.append_session_deltas(session_id, tombstones, version_id=version_id)

    def fetch_bqml_trajectories(self) -> dict[str, Any]:
        fq_view = f"`{self._fq_table('vw_lt_forecasts')}`"
        rows = self._run_query(
            f"SELECT curve_type, forecast_year, ccgt, bio_chp, bio_retro, bio_wc, "
            f"wind, solar, coal_pc, shp, coal_cfbc, data_source "
            f"FROM {fq_view} WHERE forecast_year BETWEEN 2024 AND 2046 "
            f"ORDER BY curve_type, forecast_year ASC",
            [],
        )
        grouped: dict[str, list[list[float]]] = {"CAPEX": [], "FUEL": [], "CF": []}
        years: list[int] = []
        cols = ("ccgt", "bio_chp", "bio_retro", "bio_wc", "wind", "solar", "coal_pc", "shp", "coal_cfbc")
        for r in rows:
            ctype = str(r["curve_type"]).upper()
            if ctype not in grouped:
                continue
            yr = int(r["forecast_year"])
            if ctype == "CAPEX":
                years.append(yr)
            grouped[ctype].append([float(r[c]) if r[c] is not None else 0.0 for c in cols])
        return {
            "data_source": "bigquery_ml_digital_twin",
            "years": years or list(range(2024, 2047)),
            "curves": grouped,
        }
