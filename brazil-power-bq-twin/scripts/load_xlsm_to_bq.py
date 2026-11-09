#!/usr/bin/env python3
"""One-time offline ingestion CLI: decompile a 22-tab `.xlsm` and batch-load `brazil_power_digital_twin` in BigQuery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TWIN_ROOT = Path(__file__).resolve().parents[1]
if str(TWIN_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(TWIN_ROOT / "src"))

from google.cloud import bigquery

from brazil_power_bq_twin.schema_ddl import build_digital_twin_ddl_statements
from brazil_power_bq_twin.xlsm_compiler import compile_workbook_to_twin_payload


def _batch_load_rows(
    client: bigquery.Client,
    table_id: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    job_cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        labels={"datacloud": "antigravity", "component": "bq_digital_twin_loader"},
    )
    job = client.load_table_from_json(rows, table_id, job_config=job_cfg)
    job.result()
    return len(rows)


def provision_and_load_bigquery_digital_twin(
    xlsm_path: Path,
    project_id: str = "comm-model-mod",
    dataset_id: str = "brazil_power_digital_twin",
    location: str = "us-central1",
    workbook_id: str = "brazil_power_v13",
    version_id: str = "v13_baseline",
) -> dict[str, Any]:
    """Create the isolated BigQuery dataset/tables/views, batch-load the Digital Twin, and create ARIMA_PLUS forecast view."""
    payload = compile_workbook_to_twin_payload(
        workbook_path=xlsm_path,
        workbook_id=workbook_id,
        version_id=version_id,
    )

    client = bigquery.Client(project=project_id, location=location)
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.location = location
    dataset_ref.labels = {"datacloud": "antigravity", "component": "bq_digital_twin"}
    client.create_dataset(dataset_ref, exists_ok=True)

    for ddl in build_digital_twin_ddl_statements(project_id, dataset_id):
        qcfg = bigquery.QueryJobConfig(labels={"datacloud": "antigravity"})
        client.query(ddl, job_config=qcfg).result()

    fq = f"{project_id}.{dataset_id}"
    counts = {
        "dt_workbook_versions": _batch_load_rows(client, f"{fq}.dt_workbook_versions", [payload.version_row]),
        "dt_worksheets": _batch_load_rows(client, f"{fq}.dt_worksheets", payload.worksheet_rows),
        "dt_styles": _batch_load_rows(client, f"{fq}.dt_styles", payload.style_rows),
        "dt_cells": _batch_load_rows(client, f"{fq}.dt_cells", payload.cell_rows),
        "dt_lt_trajectories": _batch_load_rows(client, f"{fq}.dt_lt_trajectories", payload.lt_trajectory_rows),
    }

    # Train isolated ARIMA_PLUS time-series model on CAPEX/FUEL/CF series (2024..2038 history -> 2039..2046 forecast)
    unpivot_train_sql = f"""
    CREATE OR REPLACE MODEL `{fq}.bqml_dt_lt_forecast`
    OPTIONS(
      model_type = 'ARIMA_PLUS',
      time_series_timestamp_col = 'series_date',
      time_series_data_col = 'metric_val',
      time_series_id_col = 'series_key',
      data_frequency = 'YEARLY',
      auto_arima = TRUE
    ) AS
    SELECT
      series_date,
      CONCAT(curve_type, '__', tech_col) AS series_key,
      metric_val
    FROM `{fq}.dt_lt_trajectories`
    UNPIVOT(metric_val FOR tech_col IN (ccgt, bio_chp, bio_retro, bio_wc, wind, solar, coal_pc, shp, coal_cfbc))
    WHERE forecast_year <= 2038
    """
    client.query(unpivot_train_sql, job_config=bigquery.QueryJobConfig(labels={"datacloud": "antigravity"})).result()

    create_forecast_view_sql = f"""
    CREATE OR REPLACE VIEW `{fq}.vw_lt_forecasts` AS
    WITH bqml_pred AS (
      SELECT
        SPLIT(series_key, '__')[OFFSET(0)] AS curve_type,
        SPLIT(series_key, '__')[OFFSET(1)] AS tech_col,
        EXTRACT(YEAR FROM forecast_timestamp) AS forecast_year,
        forecast_value
      FROM ML.FORECAST(MODEL `{fq}.bqml_dt_lt_forecast`, STRUCT(8 AS horizon, 0.90 AS confidence_level))
    ),
    pivoted_pred AS (
      SELECT
        curve_type,
        forecast_year,
        MAX(IF(tech_col = 'ccgt', forecast_value, NULL)) AS ccgt,
        MAX(IF(tech_col = 'bio_chp', forecast_value, NULL)) AS bio_chp,
        MAX(IF(tech_col = 'bio_retro', forecast_value, NULL)) AS bio_retro,
        MAX(IF(tech_col = 'bio_wc', forecast_value, NULL)) AS bio_wc,
        MAX(IF(tech_col = 'wind', forecast_value, NULL)) AS wind,
        MAX(IF(tech_col = 'solar', forecast_value, NULL)) AS solar,
        MAX(IF(tech_col = 'coal_pc', forecast_value, NULL)) AS coal_pc,
        MAX(IF(tech_col = 'shp', forecast_value, NULL)) AS shp,
        MAX(IF(tech_col = 'coal_cfbc', forecast_value, NULL)) AS coal_cfbc,
        'bigquery_ml_arima_plus' AS data_source
      FROM bqml_pred
      GROUP BY curve_type, forecast_year
    )
    SELECT
      curve_type, forecast_year, ccgt, bio_chp, bio_retro, bio_wc,
      wind, solar, coal_pc, shp, coal_cfbc, 'historical_seed' AS data_source
    FROM `{fq}.dt_lt_trajectories`
    WHERE forecast_year <= 2038
    UNION ALL
    SELECT
      curve_type, forecast_year, ccgt, bio_chp, bio_retro, bio_wc,
      wind, solar, coal_pc, shp, coal_cfbc, data_source
    FROM pivoted_pred
    WHERE forecast_year BETWEEN 2039 AND 2046
    """
    client.query(
        create_forecast_view_sql,
        job_config=bigquery.QueryJobConfig(labels={"datacloud": "antigravity"}),
    ).result()

    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "workbook_id": workbook_id,
        "version_id": version_id,
        "loaded_row_counts": counts,
        "bqml_model": f"{fq}.bqml_dt_lt_forecast",
        "forecast_view": f"{fq}.vw_lt_forecasts",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Load 22-tab .xlsm into isolated BigQuery Digital Twin dataset.")
    parser.add_argument("--xlsm-path", required=True, type=Path, help="Path to local 22-tab .xlsm/.xlsx file")
    parser.add_argument("--project-id", default="comm-model-mod")
    parser.add_argument("--dataset-id", default="brazil_power_digital_twin")
    parser.add_argument("--location", default="us-central1")
    args = parser.parse_args()

    summary = provision_and_load_bigquery_digital_twin(
        xlsm_path=args.xlsm_path.resolve(),
        project_id=args.project_id,
        dataset_id=args.dataset_id,
        location=args.location,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
