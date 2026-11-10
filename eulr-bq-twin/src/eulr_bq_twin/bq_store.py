"""BigQuery Digital Twin store for `comm-model-mod.eulr_digital_twin` (Arrow hydration + 4-Ws audit)."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from eulr_bq_twin.config import EulrTwinSettings, get_eulr_twin_settings
from eulr_bq_twin.models import (
    EulrBaselineSnapshot,
    ExternalLinkCell,
    SessionCellDelta,
    StyleMeta,
    TwinCell,
    WorksheetMeta,
)
from eulr_bq_twin.schema_ddl import validate_bq_identifier

logger = logging.getLogger(__name__)


class EulrDigitalTwinStore:
    """Thread-safe BigQuery store strictly scoped to `eulr_digital_twin`."""

    def __init__(
        self,
        settings: EulrTwinSettings | None = None,
        bq_client: bigquery.Client | None = None,
        preloaded_snapshot: EulrBaselineSnapshot | None = None,
    ) -> None:
        self.settings = settings or get_eulr_twin_settings()
        self._proj = validate_bq_identifier(self.settings.gcp_project_id)
        self._dset = validate_bq_identifier(self.settings.bq_dataset_id)
        self._bq = bq_client
        self._snapshot: EulrBaselineSnapshot | None = preloaded_snapshot
        self._lock = threading.Lock()
        # Local fallback buffer used only in offline unit tests when bq_client is None and preloaded_snapshot is set
        self._memory_deltas: dict[str, dict[tuple[str, str], SessionCellDelta]] = {}
        self._memory_audits: list[dict[str, Any]] = []

    @property
    def bq(self) -> bigquery.Client:
        if self._bq is None:
            self._bq = bigquery.Client(project=self._proj)
        return self._bq

    @property
    def fq_dataset(self) -> str:
        return f"`{self._proj}.{self._dset}"

    def _query_rows(
        self, sql: str, params: list[bigquery.ScalarQueryParameter] | None = None
    ) -> list[dict[str, Any]]:
        job_cfg = bigquery.QueryJobConfig(
            query_parameters=params or [],
            labels={"datacloud": "antigravity", "app": "eulr-bq-twin"},
        )
        job = self.bq.query(sql, job_config=job_cfg)
        try:
            arrow_tbl = job.to_arrow()
            return arrow_tbl.to_pylist()
        except Exception:
            return [dict(row.items()) for row in job.result(page_size=50_000)]

    def get_baseline_snapshot(self, force_reload: bool = False) -> EulrBaselineSnapshot:
        """Hydrate the 19-tab EULR Digital Twin + 14,162 external links from BigQuery."""
        with self._lock:
            if self._snapshot is not None and not force_reload:
                return self._snapshot

            wb_params = [
                bigquery.ScalarQueryParameter("wb_id", "STRING", self.settings.workbook_id),
                bigquery.ScalarQueryParameter("ver_id", "STRING", self.settings.base_version_id),
            ]

            ver_rows = self._query_rows(
                f"""
                SELECT named_ranges_json, calc_properties_json
                FROM {self.fq_dataset}.dt_workbook_versions`
                WHERE workbook_id = @wb_id AND version_id = @ver_id
                LIMIT 1
                """,
                wb_params,
            )
            named_ranges = (
                json.loads(ver_rows[0]["named_ranges_json"]) if ver_rows else []
            )
            calc_props = (
                json.loads(ver_rows[0]["calc_properties_json"]) if ver_rows else {"iterateCount": 10}
            )

            ws_rows = self._query_rows(
                f"""
                SELECT sheet_index, sheet_name, visibility, tab_color_rgb, max_row, max_col,
                       merged_ranges_json, col_widths_json, row_heights_json,
                       freeze_panes_coord, sheet_view_json
                FROM {self.fq_dataset}.dt_worksheets`
                WHERE workbook_id = @wb_id AND version_id = @ver_id
                ORDER BY sheet_index ASC
                """,
                wb_params,
            )
            worksheets: dict[str, WorksheetMeta] = {}
            for r in ws_rows:
                rh_raw = json.loads(r["row_heights_json"] or "{}")
                worksheets[r["sheet_name"]] = WorksheetMeta(
                    sheet_index=int(r["sheet_index"]),
                    sheet_name=r["sheet_name"],
                    visibility=r["visibility"],
                    tab_color_rgb=r.get("tab_color_rgb"),
                    max_row=int(r["max_row"]),
                    max_col=int(r["max_col"]),
                    merged_ranges=json.loads(r["merged_ranges_json"] or "[]"),
                    col_widths={k: float(v) for k, v in json.loads(r["col_widths_json"] or "{}").items()},
                    row_heights={int(k): float(v) for k, v in rh_raw.items()},
                    freeze_panes_coord=r.get("freeze_panes_coord"),
                    sheet_view=json.loads(r.get("sheet_view_json") or "{}"),
                )

            st_rows = self._query_rows(
                f"""
                SELECT style_id, number_format, font_json, fill_json, border_json, alignment_json
                FROM {self.fq_dataset}.dt_styles`
                WHERE workbook_id = @wb_id AND version_id = @ver_id
                ORDER BY style_id ASC
                """,
                wb_params,
            )
            styles: dict[int, StyleMeta] = {}
            for r in st_rows:
                sid = int(r["style_id"])
                styles[sid] = StyleMeta(
                    style_id=sid,
                    number_format=r.get("number_format"),
                    font=json.loads(r["font_json"] or "{}"),
                    fill=json.loads(r["fill_json"] or "{}"),
                    border=json.loads(r["border_json"] or "{}"),
                    alignment=json.loads(r["alignment_json"] or "{}"),
                )

            c_rows = self._query_rows(
                f"""
                SELECT sheet_name, cell_coord, row_num, col_num, data_type,
                       numeric_value, string_value, raw_formula,
                       is_array_cse, has_external_link, style_id, semantic_role
                FROM {self.fq_dataset}.dt_cells`
                WHERE workbook_id = @wb_id AND version_id = @ver_id
                """,
                wb_params,
            )
            cells_by_sheet: dict[str, dict[tuple[int, int], TwinCell]] = {
                sname: {} for sname in worksheets
            }
            for r in c_rows:
                sname = r["sheet_name"]
                rn = int(r["row_num"])
                cn = int(r["col_num"])
                nv = r.get("numeric_value")
                cells_by_sheet.setdefault(sname, {})[(rn, cn)] = TwinCell(
                    sheet_name=sname,
                    cell_coord=r["cell_coord"],
                    row_num=rn,
                    col_num=cn,
                    data_type=r["data_type"],
                    numeric_value=float(nv) if nv is not None else None,
                    string_value=r.get("string_value"),
                    raw_formula=r.get("raw_formula"),
                    is_array_cse=bool(r.get("is_array_cse", False)),
                    has_external_link=bool(r.get("has_external_link", False)),
                    style_id=int(r["style_id"]),
                    semantic_role=r["semantic_role"],
                )

            ext_rows = self._query_rows(
                f"""
                SELECT vintage_tag, link_health_tier, external_link_idx, sharepoint_url,
                       external_workbook_name, source_sheet, source_cell_a1,
                       target_sheet, target_coord, target_row, target_col,
                       baseline_cached_value, peer_live_value, is_peer_updated, raw_formula
                FROM {self.fq_dataset}.dt_external_links`
                WHERE workbook_id = @wb_id AND version_id = @ver_id
                """,
                wb_params,
            )
            ext_links: dict[tuple[str, int, int], ExternalLinkCell] = {}
            for r in ext_rows:
                tr = int(r["target_row"])
                tc = int(r["target_col"])
                pv = r.get("peer_live_value")
                ext_links[(r["target_sheet"], tr, tc)] = ExternalLinkCell(
                    vintage_tag=r["vintage_tag"],
                    link_health_tier=r["link_health_tier"],
                    external_link_idx=r["external_link_idx"],
                    sharepoint_url=r["sharepoint_url"],
                    external_workbook_name=r["external_workbook_name"],
                    source_sheet=r.get("source_sheet"),
                    source_cell_a1=r.get("source_cell_a1"),
                    target_sheet=r["target_sheet"],
                    target_coord=r["target_coord"],
                    target_row=tr,
                    target_col=tc,
                    baseline_cached_value=float(r["baseline_cached_value"]),
                    peer_live_value=float(pv) if pv is not None else None,
                    is_peer_updated=bool(r.get("is_peer_updated", False)),
                    raw_formula=r["raw_formula"],
                )

            self._snapshot = EulrBaselineSnapshot(
                workbook_id=self.settings.workbook_id,
                version_id=self.settings.base_version_id,
                worksheets=worksheets,
                styles=styles,
                cells_by_sheet=cells_by_sheet,
                external_links=ext_links,
                named_ranges=named_ranges,
                calc_properties=calc_props,
            )
            return self._snapshot

    def get_session_deltas(self, session_id: str) -> dict[tuple[str, int, int], SessionCellDelta]:
        """Fetch active non-tombstone sparse cell deltas for `session_id`."""
        if self._bq is None and self._snapshot is not None and session_id in self._memory_deltas:
            return {
                (d.sheet_name, d.row_num, d.col_num): d
                for d in self._memory_deltas[session_id].values()
                if d.delta_kind != "TOMBSTONE"
            }
        if self._bq is None and self._snapshot is not None and session_id not in self._memory_deltas:
            # In offline unit-test mode without BQ client
            if self.settings.gcp_project_id == "offline-test":
                return {}

        params = [
            bigquery.ScalarQueryParameter("sess_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("wb_id", "STRING", self.settings.workbook_id),
            bigquery.ScalarQueryParameter("ver_id", "STRING", self.settings.base_version_id),
        ]
        rows = self._query_rows(
            f"""
            SELECT sheet_name, cell_coord, row_num, col_num, delta_kind,
                   numeric_value, string_value, source_tool
            FROM {self.fq_dataset}.vw_dt_latest_session_deltas`
            WHERE session_id = @sess_id
              AND workbook_id = @wb_id
              AND base_version_id = @ver_id
              AND delta_kind != 'TOMBSTONE'
            """,
            params,
        )
        out: dict[tuple[str, int, int], SessionCellDelta] = {}
        for r in rows:
            rn = int(r["row_num"])
            cn = int(r["col_num"])
            nv = r.get("numeric_value")
            out[(r["sheet_name"], rn, cn)] = SessionCellDelta(
                sheet_name=r["sheet_name"],
                cell_coord=r["cell_coord"],
                row_num=rn,
                col_num=cn,
                delta_kind=r["delta_kind"],
                numeric_value=float(nv) if nv is not None else None,
                string_value=r.get("string_value"),
                source_tool=r["source_tool"],
            )
        return out

    def append_deltas_and_audit(
        self,
        session_id: str,
        deltas: list[SessionCellDelta],
        audit_events: list[dict[str, Any]],
    ) -> None:
        """Persist sparse session deltas and immutable 4-Ws audit events."""
        now_iso = datetime.now(UTC).isoformat()

        if self.settings.gcp_project_id == "offline-test":
            bucket = self._memory_deltas.setdefault(session_id, {})
            for d in deltas:
                bucket[(d.sheet_name, d.cell_coord)] = d
            self._memory_audits.extend(audit_events)
            return

        if deltas:
            delta_payload = [
                {
                    "session_id": session_id,
                    "workbook_id": self.settings.workbook_id,
                    "base_version_id": self.settings.base_version_id,
                    "sheet_name": d.sheet_name,
                    "cell_coord": d.cell_coord,
                    "row_num": d.row_num,
                    "col_num": d.col_num,
                    "delta_kind": d.delta_kind,
                    "numeric_value": d.numeric_value,
                    "string_value": d.string_value,
                    "source_tool": d.source_tool,
                    "updated_at": now_iso,
                }
                for d in deltas
            ]
            errs = self.bq.insert_rows_json(
                f"{self._proj}.{self._dset}.dt_scenario_deltas", delta_payload
            )
            if errs:
                raise RuntimeError(f"BigQuery dt_scenario_deltas insert error: {errs[:2]}")

        if audit_events:
            audit_payload = [
                {
                    "event_id": ev.get("event_id") or str(uuid.uuid4()),
                    "session_id": session_id,
                    "what_sheet": ev["what_sheet"],
                    "what_coord": ev["what_coord"],
                    "what_change_type": ev["what_change_type"],
                    "before_value": str(ev.get("before_value", "")),
                    "after_value": str(ev.get("after_value", "")),
                    "who_principal": ev.get("who_principal") or self.settings.default_actor,
                    "when_event_utc": now_iso,
                    "why_context": ev.get("why_context", ""),
                }
                for ev in audit_events
            ]
            errs = self.bq.insert_rows_json(
                f"{self._proj}.{self._dset}.dt_audit_events", audit_payload
            )
            if errs:
                raise RuntimeError(f"BigQuery dt_audit_events insert error: {errs[:2]}")

    def reset_session_to_baseline(self, session_id: str, actor: str, source_tool: str) -> int:
        """Write TOMBSTONE markers for all active deltas in `session_id` and record 4-Ws audit."""
        active = self.get_session_deltas(session_id)
        if not active:
            return 0
        tombstones = [
            SessionCellDelta(
                sheet_name=d.sheet_name,
                cell_coord=d.cell_coord,
                row_num=d.row_num,
                col_num=d.col_num,
                delta_kind="TOMBSTONE",
                numeric_value=None,
                string_value=None,
                source_tool=source_tool,
            )
            for d in active.values()
        ]
        self.append_deltas_and_audit(
            session_id=session_id,
            deltas=tombstones,
            audit_events=[
                {
                    "what_sheet": "WORKBOOK",
                    "what_coord": f"RESET({len(tombstones)} cells)",
                    "what_change_type": "SESSION_RESET_TO_BASELINE",
                    "before_value": f"{len(tombstones)} active overrides",
                    "after_value": "lr202409_baseline",
                    "who_principal": actor,
                    "why_context": f"{source_tool}: reset_to_baseline=True",
                }
            ],
        )
        return len(tombstones)

    def fetch_bqml_forecasts(
        self, domain_groups: list[str] | None = None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetch historical actuals (1990-2024) and ARIMA_PLUS forecasts (2025-2050) from BigQuery."""
        domains = [d.upper() for d in (domain_groups or ["MACRO", "CRUDES", "FREIGHT"])]
        if self.settings.gcp_project_id == "offline-test":
            return [], []

        params = [bigquery.ArrayQueryParameter("domains", "STRING", domains)]
        actuals = self._query_rows(
            f"""
            SELECT domain_group, series_id, series_label, units, target_sheet, target_row,
                   forecast_year, actual_value
            FROM {self.fq_dataset}.dt_driver_trajectories`
            WHERE domain_group IN UNNEST(@domains)
            ORDER BY domain_group, series_id, forecast_year
            """,
            params,
        )
        forecasts = self._query_rows(
            f"""
            SELECT domain_group, series_id, series_label, units, target_sheet, target_row,
                   forecast_year, forecast_value, lower_bound, upper_bound
            FROM {self.fq_dataset}.vw_eulr_bqml_forecasts`
            WHERE domain_group IN UNNEST(@domains)
            ORDER BY domain_group, series_id, forecast_year
            """,
            params,
        )
        return actuals, forecasts
