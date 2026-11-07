"""Provisions BigQuery dataset eulr_commodity_mod_governance, seeds tables, and provisions GCS snapshot bucket."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import bigquery, storage

from scripts.push_sheets_live import _get_google_credentials
from src.core.config import settings
from src.parser.upstream_link_hub import build_upstream_link_registry
from src.solver.upload_publisher import extract_upload_and_links_out_catalog


def deploy_bigquery_and_gcs_assets(
    project_id: str, dataset_id: str, bucket_name: str
) -> dict[str, object]:
    """Provision GCS bucket, BigQuery dataset, governance tables/views, and seed records."""
    creds = _get_google_credentials(project_id)
    storage_client = storage.Client(project=project_id, credentials=creds)
    bq_client = bigquery.Client(project=project_id, credentials=creds)

    # 1. Ensure GCS bucket exists
    bucket = storage_client.bucket(bucket_name)
    if not bucket.exists():
        bucket = storage_client.create_bucket(bucket, location=settings.gcp_region)

    # 2. Ensure BigQuery dataset exists
    ds_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    ds_ref.location = "US"
    ds_ref.labels = {
        "env": "dev",
        "app": "eulr-sheets-mod",
        "owner": "quant-platform",
        "cost-center": "commodities-r-and-d",
        "datacloud": "antigravity",
    }
    bq_client.create_dataset(ds_ref, exists_ok=True)

    # 3. Execute DDL in sql/01_governance_tables_and_views.sql
    sql_01_path = (
        Path(__file__).resolve().parents[1] / "sql" / "01_governance_tables_and_views.sql"
    )
    sql_01 = sql_01_path.read_text(encoding="utf-8")
    job_config = bigquery.QueryJobConfig(labels={"datacloud": "antigravity"})
    bq_client.query(sql_01, job_config=job_config).result()

    # 4. Export upstream_external_series and eulr_upload_series JSONL and load into BigQuery
    now_iso = datetime.now(UTC).isoformat()
    reg = build_upstream_link_registry(
        settings.resolved_seed_path, settings.resolved_references_dir
    )
    up_rows = [
        {
            "vintage_tag": r.vintage_tag,
            "link_health_tier": r.link_health_tier,
            "external_link_idx": r.external_link_idx,
            "sharepoint_url": r.sharepoint_url,
            "external_workbook_name": r.external_workbook_name,
            "source_sheet": r.source_sheet,
            "source_cell_a1": r.source_cell_a1,
            "target_eulr_sheet": r.target_eulr_sheet,
            "target_cell_a1": r.target_cell_a1,
            "baseline_cached_value": r.baseline_cached_value,
            "active_value": r.peer_live_value
            if r.is_peer_updated and r.peer_live_value is not None
            else r.baseline_cached_value,
            "value_source": "peer_xlsx" if r.is_peer_updated else "eulr_baseline_cached",
            "updated_at": now_iso,
        }
        for r in reg.records
    ]

    load_cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        labels={"datacloud": "antigravity"},
    )
    bq_client.load_table_from_json(
        up_rows,
        f"{project_id}.{dataset_id}.upstream_external_series",
        job_config=load_cfg,
    ).result()

    upload_rows, links_rows = extract_upload_and_links_out_catalog()
    pub_rows = [
        {
            "vintage_tag": "202409",
            "row_idx": u.row_idx,
            "series_mnemonic": u.series_mnemonic,
            "description": u.description,
            "unit": u.unit,
            "value_2024": u.value_2024,
            "value_2025": u.value_2025,
            "value_2030": u.value_2030,
            "value_2050": u.value_2050,
            "published_at": now_iso,
        }
        for u in upload_rows
    ]
    bq_client.load_table_from_json(
        pub_rows,
        f"{project_id}.{dataset_id}.eulr_upload_series",
        job_config=load_cfg,
    ).result()

    links_payload = [
        {
            "vintage_tag": "202409",
            "row_idx": lo.row_idx,
            "series_mnemonic": lo.series_mnemonic,
            "description": lo.description,
            "unit": lo.unit,
            "value_2024": lo.value_2024,
            "value_2025": lo.value_2025,
            "value_2030": lo.value_2030,
            "value_2050": lo.value_2050,
            "published_at": now_iso,
        }
        for lo in links_rows
    ]
    bq_client.load_table_from_json(
        links_payload,
        f"{project_id}.{dataset_id}.eulr_links_out",
        job_config=load_cfg,
    ).result()

    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "bucket_name": bucket_name,
        "upstream_series_loaded": len(up_rows),
        "upload_series_loaded": len(pub_rows),
        "links_out_series_loaded": len(links_payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision EULR BigQuery & GCS governance assets.")
    parser.add_argument("--project-id", default=settings.gcp_project_id)
    args = parser.parse_args()
    res = deploy_bigquery_and_gcs_assets(
        project_id=args.project_id,
        dataset_id=settings.bigquery_dataset,
        bucket_name=settings.gcs_snapshot_bucket,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
