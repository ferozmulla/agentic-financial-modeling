"""CLI utility to run a structural checkpoint ingestion against the seed .xlsm."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from src.core.config import get_settings
from src.db.bigquery_sink import BigQueryAnalyticalSink
from src.db.session import get_session_factory, init_db_schema
from src.ingestion.checkpoint_pipeline import execute_checkpoint_pipeline
from src.storage.snapshot_store import get_snapshot_store


async def _run(xlsm_path: str, spreadsheet_id: str, commit_message: str) -> int:
    await init_db_schema()
    factory = get_session_factory()
    store = get_snapshot_store()
    bq_sink = BigQueryAnalyticalSink()
    raw_bytes = Path(xlsm_path).read_bytes()

    async with factory() as session, session.begin():
        resp, _graph = await execute_checkpoint_pipeline(
            session=session,
            spreadsheet_id=spreadsheet_id,
            raw_bytes=raw_bytes,
            commit_comment=commit_message,
            who_google_user="cli@comm-model-mod.iam.gserviceaccount.com",
            snapshot_store=store,
            bq_sink=bq_sink,
        )

    summary = resp.model_dump(exclude={"audit_events"})
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run Pillar B structural checkpoint ingestion on an .xlsm workbook."
    )
    parser.add_argument(
        "--xlsm",
        default=str(settings.seed_workbook_path),
        help="Path to the .xlsm workbook",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default="brazil_tt_v13_seed",
        help="Logical spreadsheet identifier",
    )
    parser.add_argument(
        "--message",
        default="Initial baseline checkpoint ingestion",
        help="Checkpoint commit message",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.xlsm, args.spreadsheet_id, args.message))


if __name__ == "__main__":
    sys.exit(main())
