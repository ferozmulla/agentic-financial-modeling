#!/usr/bin/env python3
"""Compile `Latinlr202409` Golden Vault workbook into BigQuery `latinlr202409_digital_twin` + `ARIMA_PLUS`."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from google.cloud import bigquery, storage

from latinlr202409_bq_twin.config import get_twin_settings
from latinlr202409_bq_twin.schema_ddl import (
    build_bqml_arima_ddl,
    build_digital_twin_ddl,
    validate_bq_identifier,
)
from latinlr202409_bq_twin.xlsx_compiler import compile_workbook


def _load_rows(bq: bigquery.Client, table_fqn: str, rows: list[dict], truncate: bool = True) -> None:
    if not rows:
        return
    cfg = bigquery.LoadJobConfig(
        write_disposition=(
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if truncate
            else bigquery.WriteDisposition.WRITE_APPEND
        )
    )
    bq.load_table_from_json(rows, table_fqn, job_config=cfg).result()


def main() -> int:
    parser = argparse.ArgumentParser(description="Load latinlr202409 Digital Twin to BigQuery.")
    parser.add_argument("--xlsx-path", type=str, default="")
    parser.add_argument("--skip-bqml", action="store_true")
    args = parser.parse_args()

    settings = get_twin_settings()
    proj = validate_bq_identifier(settings.gcp_project_id)
    dset = validate_bq_identifier(settings.bq_dataset_id)

    bq = bigquery.Client(project=proj)
    gcs = storage.Client(project=proj)

    ds_ref = bigquery.Dataset(f"{proj}.{dset}")
    ds_ref.location = settings.gcp_region
    bq.create_dataset(ds_ref, exists_ok=True)

    for stmt in build_digital_twin_ddl(proj, dset):
        bq.query(stmt).result()

    with tempfile.TemporaryDirectory() as tmp:
        if args.xlsx_path and Path(args.xlsx_path).exists():
            wb_path = Path(args.xlsx_path)
        else:
            wb_path = Path(tmp) / "Latinlr202409_remediated.xlsx"
            bucket = gcs.bucket(settings.gcs_vault_bucket)
            blob = bucket.blob("golden-seed/latinlr202409/Latinlr202409_remediated.xlsx")
            if not blob.exists():
                blob = bucket.blob("uploads/upl-a691d13eb8b2/Latinlr202409_remediated.xlsx")
            blob.download_to_filename(str(wb_path))

        payload = compile_workbook(wb_path, settings.workbook_id, settings.base_version_id)

    fq = f"{proj}.{dset}"
    _load_rows(bq, f"{fq}.dt_workbook_versions", [payload.version_row])
    _load_rows(bq, f"{fq}.dt_worksheets", payload.worksheet_rows)
    _load_rows(bq, f"{fq}.dt_styles", payload.style_rows)
    chunk = 100_000
    for i in range(0, len(payload.cell_rows), chunk):
        _load_rows(bq, f"{fq}.dt_cells", payload.cell_rows[i : i + chunk], truncate=(i == 0))
    _load_rows(bq, f"{fq}.dt_external_links", payload.external_link_rows)
    _load_rows(bq, f"{fq}.dt_driver_trajectories", payload.driver_trajectory_rows)

    if not args.skip_bqml and payload.driver_trajectory_rows:
        for stmt in build_bqml_arima_ddl(proj, dset):
            bq.query(stmt).result()

    print(f"Loaded {len(payload.cell_rows):,} cells into {fq}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
