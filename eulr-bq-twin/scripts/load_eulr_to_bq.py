#!/usr/bin/env python3
"""One-time offline decompiler & BigQuery loader for `comm-model-mod.eulr_digital_twin`."""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from google.cloud import bigquery, storage

from eulr_bq_twin.config import get_eulr_twin_settings
from eulr_bq_twin.schema_ddl import (
    build_eulr_bqml_training_ddl,
    build_eulr_digital_twin_ddl,
    validate_bq_identifier,
)
from eulr_bq_twin.xlsx_compiler import PEER_WORKBOOK_BY_INDEX, compile_eulr_workbook


def _download_vault_seeds_if_needed(
    gcs_client: storage.Client,
    bucket_name: str,
    local_xlsx: Path | None,
    local_refs_dir: Path | None,
    tmp_dir: Path,
) -> tuple[Path, Path]:
    if local_xlsx and local_xlsx.exists():
        seed_path = local_xlsx
    else:
        seed_path = tmp_dir / "Eulr202409.xlsx"
        bucket = gcs_client.bucket(bucket_name)
        bucket.blob("golden-seed/Eulr202409.xlsx").download_to_filename(str(seed_path))

    if local_refs_dir and local_refs_dir.exists():
        refs_dir = local_refs_dir
    else:
        refs_dir = tmp_dir / "references"
        refs_dir.mkdir(parents=True, exist_ok=True)
        bucket = gcs_client.bucket(bucket_name)
        for fname in PEER_WORKBOOK_BY_INDEX.values():
            blob = bucket.blob(f"golden-seed/references/{fname}")
            if blob.exists():
                blob.download_to_filename(str(refs_dir / fname))
    return seed_path, refs_dir


def _load_json_rows(
    bq: bigquery.Client,
    table_fqn: str,
    rows: list[dict],
    write_disposition: str = bigquery.WriteDisposition.WRITE_TRUNCATE,
) -> None:
    if not rows:
        return
    cfg = bigquery.LoadJobConfig(
        write_disposition=write_disposition,
        labels={"datacloud": "antigravity", "app": "eulr-bq-twin"},
    )
    job = bq.load_table_from_json(rows, table_fqn, job_config=cfg)
    job.result()


def main() -> int:
    parser = argparse.ArgumentParser(description="Load EULR Digital Twin & train BQML models.")
    parser.add_argument("--xlsx-path", type=str, default="", help="Optional local Eulr202409.xlsx path")
    parser.add_argument("--refs-dir", type=str, default="", help="Optional local peer references dir")
    parser.add_argument("--skip-bqml", action="store_true", help="Skip ARIMA_PLUS model training")
    args = parser.parse_args()

    settings = get_eulr_twin_settings()
    proj = validate_bq_identifier(settings.gcp_project_id)
    dset = validate_bq_identifier(settings.bq_dataset_id)

    bq = bigquery.Client(project=proj)
    gcs = storage.Client(project=proj)
    job_cfg = bigquery.QueryJobConfig(labels={"datacloud": "antigravity", "app": "eulr-bq-twin"})

    t0 = time.perf_counter()
    print(f"[1/4] Applying BigQuery DDL in `{proj}.{dset}`...")
    for stmt in build_eulr_digital_twin_ddl(proj, dset):
        bq.query(stmt, job_config=job_cfg).result()

    with tempfile.TemporaryDirectory() as tmp:
        seed_path, refs_dir = _download_vault_seeds_if_needed(
            gcs_client=gcs,
            bucket_name=settings.gcs_vault_bucket,
            local_xlsx=Path(args.xlsx_path) if args.xlsx_path else None,
            local_refs_dir=Path(args.refs_dir) if args.refs_dir else None,
            tmp_dir=Path(tmp),
        )
        print(f"[2/4] Compiling `{seed_path.name}` + peer links from `{refs_dir}`...")
        payload = compile_eulr_workbook(
            xlsx_path=seed_path,
            workbook_id=settings.workbook_id,
            version_id=settings.base_version_id,
            references_dir=refs_dir,
        )

    peer_updated = sum(1 for r in payload.external_link_rows if r["is_peer_updated"])
    print(
        f"      Compiled {len(payload.worksheet_rows)} sheets | "
        f"{len(payload.style_rows)} styles | "
        f"{len(payload.cell_rows):,} cells | "
        f"{len(payload.external_link_rows):,} ext links ({peer_updated:,} peer-updated) | "
        f"{len(payload.driver_trajectory_rows)} driver actuals."
    )

    print(f"[3/4] Batch-loading Digital Twin tables into `{proj}.{dset}`...")
    fq = f"{proj}.{dset}"
    _load_json_rows(bq, f"{fq}.dt_workbook_versions", [payload.version_row])
    _load_json_rows(bq, f"{fq}.dt_worksheets", payload.worksheet_rows)
    _load_json_rows(bq, f"{fq}.dt_styles", payload.style_rows)
    # Chunk dt_cells in 150k-row batches for fast reliable JSON load
    chunk_sz = 150_000
    for idx in range(0, len(payload.cell_rows), chunk_sz):
        disp = (
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if idx == 0
            else bigquery.WriteDisposition.WRITE_APPEND
        )
        _load_json_rows(bq, f"{fq}.dt_cells", payload.cell_rows[idx : idx + chunk_sz], disp)
    _load_json_rows(bq, f"{fq}.dt_external_links", payload.external_link_rows)
    _load_json_rows(bq, f"{fq}.dt_driver_trajectories", payload.driver_trajectory_rows)

    if not args.skip_bqml:
        print(f"[4/4] Training 3 BigQuery ML ARIMA_PLUS models (`MACRO`, `CRUDES`, `FREIGHT`)...")
        for stmt in build_eulr_bqml_training_ddl(proj, dset):
            bq.query(stmt, job_config=job_cfg).result()
    else:
        print("[4/4] Skipping BQML model training (--skip-bqml).")

    elapsed = round(time.perf_counter() - t0, 2)
    print(f"Done in {elapsed}s!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
