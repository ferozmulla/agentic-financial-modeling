"""Parameterized BigQuery Digital Twin Store & 4-Ws Audit Event Writer reference template."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from .schema_ddl import validate_bq_identifier


class BaseDigitalTwinStore:
    """Thread-safe BigQuery Digital Twin persistence using parameterized queries exclusively."""

    def __init__(self, project_id: str, dataset_id: str, workbook_id: str, base_version_id: str) -> None:
        self.project_id = validate_bq_identifier(project_id)
        self.dataset_id = validate_bq_identifier(dataset_id)
        self.workbook_id = validate_bq_identifier(workbook_id)
        self.base_version_id = validate_bq_identifier(base_version_id)
        self._fq = f"`{self.project_id}.{self.dataset_id}"
        self._client: bigquery.Client | None = None

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client(project=self.project_id)
        return self._client

    def get_session_deltas(self, session_id: str) -> dict[tuple[str, str], dict[str, Any]]:
        """Fetch latest active non-tombstone cell overrides for `session_id`."""
        sql = f"""
        SELECT sheet_name, cell_coord, delta_kind, numeric_value, string_value
        FROM {self._fq}.vw_dt_latest_session_deltas`
        WHERE session_id = @session_id
          AND workbook_id = @workbook_id
          AND base_version_id = @base_version_id
        """
        cfg = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
                bigquery.ScalarQueryParameter("workbook_id", "STRING", self.workbook_id),
                bigquery.ScalarQueryParameter("base_version_id", "STRING", self.base_version_id),
            ],
            labels={"datacloud": "antigravity", "component": "digital-twin-store"},
        )
        overlays: dict[tuple[str, str], dict[str, Any]] = {}
        for row in self.client.query(sql, job_config=cfg).result():
            if row["delta_kind"] != "RESET_TOMBSTONE":
                overlays[(row["sheet_name"], row["cell_coord"])] = dict(row)
        return overlays

    def record_deltas_and_audit(
        self,
        session_id: str,
        deltas: list[dict[str, Any]],
        who_principal: str,
        source_tool: str,
        why_context: str,
    ) -> int:
        """Append session deltas and corresponding 4-Ws (`Who`, `What`, `When`, `Why`) audit rows."""
        if not deltas:
            return 0
        now_iso = datetime.now(UTC).isoformat()
        delta_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []

        for item in deltas:
            delta_rows.append(
                {
                    "session_id": session_id,
                    "workbook_id": self.workbook_id,
                    "base_version_id": self.base_version_id,
                    "sheet_name": str(item["sheet_name"]),
                    "cell_coord": str(item["cell_coord"]),
                    "row_num": int(item["row_num"]),
                    "col_num": int(item["col_num"]),
                    "delta_kind": str(item.get("delta_kind", "USER_OVERRIDE")),
                    "numeric_value": item.get("numeric_value"),
                    "string_value": item.get("string_value"),
                    "source_tool": source_tool,
                    "updated_at": now_iso,
                }
            )
            audit_rows.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "what_sheet": str(item["sheet_name"]),
                    "what_coord": str(item["cell_coord"]),
                    "what_change_type": str(item.get("delta_kind", "USER_OVERRIDE")),
                    "before_value": str(item.get("before_value", "")),
                    "after_value": str(
                        item.get("numeric_value")
                        if item.get("numeric_value") is not None
                        else item.get("string_value", "")
                    ),
                    "who_principal": who_principal,
                    "when_event_utc": now_iso,
                    "why_context": why_context,
                }
            )

        load_cfg = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            labels={"datacloud": "antigravity", "component": "digital-twin-store"},
        )
        fq_clean = f"{self.project_id}.{self.dataset_id}"
        self.client.load_table_from_json(delta_rows, f"{fq_clean}.dt_scenario_deltas", job_config=load_cfg).result()
        self.client.load_table_from_json(audit_rows, f"{fq_clean}.dt_audit_events", job_config=load_cfg).result()
        return len(delta_rows)
