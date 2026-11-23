"""Parameterized BigQuery Digital Twin, 4-Ws Governance & BQML ARIMA_PLUS DDL template."""

from __future__ import annotations

import re

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def validate_bq_identifier(identifier: str) -> str:
    cleaned = identifier.strip()
    if not _SAFE_ID_RE.match(cleaned):
        raise ValueError(f"Unsafe BigQuery identifier: {identifier!r}")
    return cleaned


def build_digital_twin_ddl(project_id: str, dataset_id: str) -> list[str]:
    """Generate partitioned and clustered BigQuery Digital Twin + 4-Ws Audit DDL statements."""
    proj = validate_bq_identifier(project_id)
    dset = validate_bq_identifier(dataset_id)
    fq = f"`{proj}.{dset}"

    return [
        f"CREATE SCHEMA IF NOT EXISTS `{proj}.{dset}` OPTIONS(location = 'us-central1')",
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_workbook_versions` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          version_label STRING NOT NULL,
          total_sheets INT64 NOT NULL,
          total_cells INT64 NOT NULL,
          total_formulas INT64 NOT NULL,
          named_ranges_json STRING NOT NULL,
          calc_properties_json STRING NOT NULL,
          created_at TIMESTAMP NOT NULL
        )
        CLUSTER BY workbook_id, version_id
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_worksheets` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          sheet_index INT64 NOT NULL,
          sheet_name STRING NOT NULL,
          visibility STRING NOT NULL,
          tab_color_rgb STRING,
          max_row INT64 NOT NULL,
          max_col INT64 NOT NULL,
          merged_ranges_json STRING NOT NULL,
          col_widths_json STRING NOT NULL,
          row_heights_json STRING NOT NULL,
          freeze_panes_coord STRING
        )
        CLUSTER BY workbook_id, version_id, sheet_index
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_styles` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          style_id INT64 NOT NULL,
          number_format STRING,
          font_json STRING NOT NULL,
          fill_json STRING NOT NULL,
          border_json STRING NOT NULL,
          alignment_json STRING NOT NULL
        )
        CLUSTER BY workbook_id, version_id, style_id
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_cells` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          sheet_name STRING NOT NULL,
          cell_coord STRING NOT NULL,
          row_num INT64 NOT NULL,
          col_num INT64 NOT NULL,
          data_type STRING NOT NULL,
          numeric_value FLOAT64,
          string_value STRING,
          raw_formula STRING,
          is_array_cse BOOL NOT NULL,
          has_external_link BOOL NOT NULL,
          style_id INT64 NOT NULL,
          semantic_role STRING NOT NULL
        )
        CLUSTER BY workbook_id, version_id, sheet_name, row_num
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_scenario_deltas` (
          session_id STRING NOT NULL,
          workbook_id STRING NOT NULL,
          base_version_id STRING NOT NULL,
          sheet_name STRING NOT NULL,
          cell_coord STRING NOT NULL,
          row_num INT64 NOT NULL,
          col_num INT64 NOT NULL,
          delta_kind STRING NOT NULL,
          numeric_value FLOAT64,
          string_value STRING,
          source_tool STRING NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        PARTITION BY DATE(updated_at)
        CLUSTER BY session_id, sheet_name
        """,
        f"""
        CREATE OR REPLACE VIEW {fq}.vw_dt_latest_session_deltas` AS
        SELECT *
        FROM {fq}.dt_scenario_deltas`
        QUALIFY ROW_NUMBER() OVER (
          PARTITION BY session_id, workbook_id, base_version_id, sheet_name, cell_coord
          ORDER BY updated_at DESC
        ) = 1
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_audit_events` (
          event_id STRING NOT NULL,
          session_id STRING NOT NULL,
          what_sheet STRING NOT NULL,
          what_coord STRING NOT NULL,
          what_change_type STRING NOT NULL,
          before_value STRING,
          after_value STRING,
          who_principal STRING NOT NULL,
          when_event_utc TIMESTAMP NOT NULL,
          why_context STRING NOT NULL
        )
        PARTITION BY DATE(when_event_utc)
        CLUSTER BY session_id, what_sheet
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_driver_trajectories` (
          domain_group STRING NOT NULL,
          series_id STRING NOT NULL,
          series_label STRING NOT NULL,
          units STRING NOT NULL,
          target_sheet STRING NOT NULL,
          target_row INT64 NOT NULL,
          forecast_year INT64 NOT NULL,
          series_date DATE NOT NULL,
          actual_value FLOAT64 NOT NULL
        )
        CLUSTER BY domain_group, series_id, forecast_year
        """,
    ]


def build_bqml_arima_ddl(project_id: str, dataset_id: str, horizon: int = 25) -> list[str]:
    """Generate BigQuery ML ARIMA_PLUS model and forecast view DDL statements."""
    proj = validate_bq_identifier(project_id)
    dset = validate_bq_identifier(dataset_id)
    safe_horizon = max(1, min(int(horizon), 50))
    fq = f"`{proj}.{dset}"

    return [
        f"""
        CREATE OR REPLACE MODEL {fq}.bqml_driver_forecast`
        OPTIONS(
          MODEL_TYPE = 'ARIMA_PLUS',
          TIME_SERIES_TIMESTAMP_COL = 'series_date',
          TIME_SERIES_DATA_COL = 'actual_value',
          TIME_SERIES_ID_COL = 'series_id',
          DATA_FREQUENCY = 'YEARLY',
          HORIZON = {safe_horizon},
          AUTO_ARIMA = TRUE,
          DECOMPOSE_TIME_SERIES = TRUE
        ) AS
        SELECT series_date, series_id, actual_value
        FROM {fq}.dt_driver_trajectories`
        """,
        f"""
        CREATE OR REPLACE VIEW {fq}.vw_bqml_forecasts` AS
        SELECT
          series_id,
          EXTRACT(YEAR FROM forecast_timestamp) AS forecast_year,
          forecast_value,
          prediction_interval_lower_bound AS lower_bound,
          prediction_interval_upper_bound AS upper_bound
        FROM ML.FORECAST(
          MODEL {fq}.bqml_driver_forecast`,
          STRUCT({safe_horizon} AS horizon, 0.90 AS confidence_level)
        )
        """,
    ]
