"""BigQuery analytical sink (ENV=gcp in us-central1) with local JSONL mirror (ENV=local)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.config import Settings, get_settings
from src.schemas.audit import AuditEventRecord


class BigQueryAnalyticalSink:
    """Streams immutable 4-Ws audit events and solver telemetry to BigQuery or local JSONL."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.local_dir: Path = self.settings.local_bq_sink_dir
        self.local_dir.mkdir(parents=True, exist_ok=True)

    def stream_audit_events(self, events: list[AuditEventRecord]) -> None:
        """Append 4-Ws audit events to local JSONL mirror and (in ENV=gcp) BigQuery table."""
        if not events:
            return
        rows = [e.model_dump() for e in events]
        jsonl_path = self.local_dir / "audit_events.jsonl"
        with jsonl_path.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")

        if self.settings.env == "gcp":
            from google.cloud import bigquery  # type: ignore[import-untyped]

            client = bigquery.Client(
                project=self.settings.gcp_project_id,
                location=self.settings.bq_location,
            )
            table_id = (
                f"{self.settings.gcp_project_id}.{self.settings.bq_dataset_id}.audit_events"
            )
            bq_rows = []
            for e in events:
                d = e.model_dump(mode="json")
                d["before_state"] = json.dumps(d.get("before_state") or {})
                d["after_state"] = json.dumps(d.get("after_state") or {})
                bq_rows.append(d)
            client.insert_rows_json(table_id, bq_rows)

    def stream_solver_telemetry(self, telemetry_row: dict[str, Any]) -> None:
        """Append solver execution telemetry row to local JSONL mirror and BigQuery."""
        jsonl_path = self.local_dir / "solver_run_telemetry.jsonl"
        with jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(telemetry_row, default=str) + "\n")

        if self.settings.env == "gcp":
            from google.cloud import bigquery  # type: ignore[import-untyped]

            client = bigquery.Client(
                project=self.settings.gcp_project_id,
                location=self.settings.bq_location,
            )
            table_id = (
                f"{self.settings.gcp_project_id}.{self.settings.bq_dataset_id}.solver_run_telemetry"
            )
            bq_row = json.loads(json.dumps(telemetry_row, default=str))
            client.insert_rows_json(table_id, [bq_row])
