"""Idempotent BigQuery DDL statements for the isolated `brazil_power_digital_twin` dataset."""

from __future__ import annotations

import re

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

EXPECTED_22_TABS: tuple[str, ...] = (
    "Version Control",
    "General",
    "Output_1",
    "Output_2",
    "Output_3",
    "_01_CF",
    "_02_CF",
    "_03_CF",
    "_04_CF",
    "_05_CF",
    "_06_CF",
    "_07_CF",
    "_08_CF",
    "_09_CF",
    "_10_CF",
    "_11_CF",
    "_12_CF",
    "_CAPEX 01",
    "CVU_GF",
    "LT Capex",
    "LT Fuel",
    "LT CF",
)


def _validate_bq_id(identifier: str) -> str:
    cleaned = identifier.strip()
    if not _SAFE_ID_RE.match(cleaned):
        raise ValueError(f"Unsafe BigQuery identifier: '{identifier}'")
    return cleaned


def build_digital_twin_ddl_statements(project_id: str, dataset_id: str) -> list[str]:
    """Generate partitioned and clustered BigQuery DDL statements for the Digital Twin schema."""
    proj = _validate_bq_id(project_id)
    dset = _validate_bq_id(dataset_id)
    fq = f"`{proj}.{dset}"

    return [
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_workbook_versions` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          version_label STRING NOT NULL,
          total_sheets INT64 NOT NULL,
          total_cells INT64 NOT NULL,
          named_ranges_json STRING NOT NULL,
          solver_parameters_json STRING NOT NULL,
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
        CLUSTER BY session_id, sheet_name
        """.replace("CLUSTER BY session_id, sheet_name", "CLUSTER BY session_id, what_sheet"),
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_lt_trajectories` (
          curve_type STRING NOT NULL,
          forecast_year INT64 NOT NULL,
          series_date DATE NOT NULL,
          ccgt FLOAT64,
          bio_chp FLOAT64,
          bio_retro FLOAT64,
          bio_wc FLOAT64,
          wind FLOAT64,
          solar FLOAT64,
          coal_pc FLOAT64,
          shp FLOAT64,
          coal_cfbc FLOAT64,
          data_source STRING NOT NULL
        )
        CLUSTER BY curve_type, forecast_year
        """,
    ]
