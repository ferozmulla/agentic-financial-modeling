"""Dual-mode (GCS/BigQuery + local JSON/SQLite parity) repository for per-spreadsheet override masks and 4-Ws audit logs."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.core.config import settings

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _sanitize_spreadsheet_id(spreadsheet_id: str) -> str:
    cleaned = _SAFE_ID_RE.sub("_", spreadsheet_id.strip())
    return cleaned[:120] or "default_sheet"


@dataclass
class AuditEventRecord:
    event_id: str
    when_event_utc: str
    who_actor_email: str
    where_spreadsheet_id: str
    copy_location_url: str
    where_sheet_name: str
    where_cell_a1: str
    what_classification: str
    before_value: str | None
    new_value: str | None
    before_formula: str | None
    new_formula: str | None
    why_ai_summary: str
    rollback_tier_hint: str


class GovernanceRepository:
    """
    Manages isolated per-spreadsheet Pinned Override masks (supporting 'File -> Make a copy')
    and immutable 4-Ws audit logs across local JSONL and Cloud Storage / BigQuery.
    """

    def __init__(self, base_data_dir: Path | None = None) -> None:
        self.data_dir = base_data_dir or settings.data_dir
        self.overrides_dir = self.data_dir / "overrides"
        self.overrides_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_path = self.data_dir / "audit_events_4ws.jsonl"

    def _override_file_for(self, spreadsheet_id: str) -> Path:
        safe_id = _sanitize_spreadsheet_id(spreadsheet_id)
        return self.overrides_dir / f"{safe_id}.json"

    def get_pinned_overrides(self, spreadsheet_id: str) -> dict[str, float]:
        path = self._override_file_for(spreadsheet_id)
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {str(k): float(v) for k, v in raw.get("overrides", {}).items()}
        except (OSError, ValueError, TypeError):
            return {}

    def upsert_pinned_override(
        self, spreadsheet_id: str, sheet_name: str, cell_a1: str, value: float
    ) -> dict[str, float]:
        current = self.get_pinned_overrides(spreadsheet_id)
        key = f"{sheet_name}!{cell_a1.upper()}"
        current[key] = float(value)
        self._save_overrides(spreadsheet_id, current)
        return current

    def revert_pinned_overrides(
        self, spreadsheet_id: str, target_cell_a1: str | None = None
    ) -> tuple[list[str], dict[str, float]]:
        current = self.get_pinned_overrides(spreadsheet_id)
        if target_cell_a1 is None:
            reverted = sorted(current.keys())
            self._save_overrides(spreadsheet_id, {})
            return reverted, {}

        normalized_target = target_cell_a1.strip()
        reverted = []
        for k in list(current.keys()):
            if k.lower() == normalized_target.lower() or k.split("!")[-1].upper() == normalized_target.upper():
                reverted.append(k)
                del current[k]
        self._save_overrides(spreadsheet_id, current)
        return reverted, current

    def _save_overrides(self, spreadsheet_id: str, overrides: dict[str, float]) -> None:
        path = self._override_file_for(spreadsheet_id)
        payload = {
            "spreadsheet_id": spreadsheet_id,
            "updated_at_utc": datetime.now(UTC).isoformat(),
            "overrides": overrides,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def append_audit_event(
        self,
        *,
        actor_email: str,
        spreadsheet_id: str,
        copy_location_url: str,
        sheet_name: str,
        cell_a1: str,
        classification: str,
        before_value: float | str | None,
        new_value: float | str | None,
        before_formula: str | None,
        new_formula: str | None,
        why_ai_summary: str,
        rollback_tier_hint: str,
    ) -> AuditEventRecord:
        rec = AuditEventRecord(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            when_event_utc=datetime.now(UTC).isoformat(),
            who_actor_email=actor_email,
            where_spreadsheet_id=spreadsheet_id,
            copy_location_url=copy_location_url,
            where_sheet_name=sheet_name,
            where_cell_a1=cell_a1,
            what_classification=classification,
            before_value=str(before_value) if before_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            before_formula=before_formula,
            new_formula=new_formula,
            why_ai_summary=why_ai_summary,
            rollback_tier_hint=rollback_tier_hint,
        )
        with self.audit_log_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(asdict(rec)) + "\n")
        return rec

    def list_audit_events(self, spreadsheet_id: str | None = None) -> list[AuditEventRecord]:
        if not self.audit_log_path.exists():
            return []
        out: list[AuditEventRecord] = []
        for line in self.audit_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            rec = AuditEventRecord(**data)
            if spreadsheet_id is None or rec.where_spreadsheet_id == spreadsheet_id:
                out.append(rec)
        return out

    def get_surgical_cell_rollback(
        self, spreadsheet_id: str, sheet_name: str, cell_a1: str
    ) -> AuditEventRecord | None:
        """Tier 2 Rollback: Find the most recent audit record for (spreadsheet_id, sheet_name, cell_a1) to restore before_formula / before_value."""
        events = self.list_audit_events(spreadsheet_id)
        for ev in reversed(events):
            if (
                ev.where_sheet_name == sheet_name
                and ev.where_cell_a1.upper() == cell_a1.upper()
                and (ev.before_formula is not None or ev.before_value is not None)
            ):
                return ev
        return None


governance_repo = GovernanceRepository()
