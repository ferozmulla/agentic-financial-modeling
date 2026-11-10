"""Idempotent BigQuery DDL statements for `comm-model-mod.eulr_digital_twin`."""

from __future__ import annotations

import re

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# 18 Core Analytical & Pricing Tabs (default .xlsx export)
CORE_18_EULR_TABS: tuple[str, ...] = (
    "Info",
    "Input",
    "Freight",
    "Crudes",
    "KeyInputs",
    "Op_Cost",
    "NWE Cif",
    "MED Cif",
    "NWE Fob",
    "MED Fob",
    "Links out",
    "IMOfuels",
    "Carbon",
    "HCK naphtha revamp",
    "Yields",
    "2015 NWE HCK IRR",
    "Checks",
    "ULSD-GO_spread_econs",
)

# All 19 Active Tabs (adds downstream 93,935-cell UPLOAD staging sheet; retires shooju_addin)
ACTIVE_19_EULR_TABS: tuple[str, ...] = (
    "Info",
    "Input",
    "Freight",
    "Crudes",
    "KeyInputs",
    "Op_Cost",
    "NWE Cif",
    "MED Cif",
    "NWE Fob",
    "MED Fob",
    "Links out",
    "IMOfuels",
    "Carbon",
    "UPLOAD",
    "HCK naphtha revamp",
    "Yields",
    "2015 NWE HCK IRR",
    "Checks",
    "ULSD-GO_spread_econs",
)


def validate_bq_identifier(identifier: str) -> str:
    cleaned = identifier.strip()
    if not _SAFE_ID_RE.match(cleaned):
        raise ValueError(f"Unsafe BigQuery identifier: {identifier!r}")
    return cleaned


def build_eulr_digital_twin_ddl(project_id: str, dataset_id: str) -> list[str]:
    """Generate partitioned and clustered BigQuery DDL statements for `eulr_digital_twin`."""
    proj = validate_bq_identifier(project_id)
    dset = validate_bq_identifier(dataset_id)
    fq = f"`{proj}.{dset}"

    return [
        f"""
        CREATE TABLE IF NOT EXISTS {fq}.dt_workbook_versions` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          version_label STRING NOT NULL,
          total_sheets INT64 NOT NULL,
          total_cells INT64 NOT NULL,
          total_formulas INT64 NOT NULL,
          total_external_links INT64 NOT NULL,
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
          freeze_panes_coord STRING,
          sheet_view_json STRING NOT NULL
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
        CREATE TABLE IF NOT EXISTS {fq}.dt_external_links` (
          workbook_id STRING NOT NULL,
          version_id STRING NOT NULL,
          vintage_tag STRING NOT NULL,
          link_health_tier STRING NOT NULL,
          external_link_idx STRING NOT NULL,
          sharepoint_url STRING NOT NULL,
          external_workbook_name STRING NOT NULL,
          source_sheet STRING,
          source_cell_a1 STRING,
          target_sheet STRING NOT NULL,
          target_coord STRING NOT NULL,
          target_row INT64 NOT NULL,
          target_col INT64 NOT NULL,
          baseline_cached_value FLOAT64 NOT NULL,
          peer_live_value FLOAT64,
          is_peer_updated BOOL NOT NULL,
          raw_formula STRING NOT NULL
        )
        CLUSTER BY workbook_id, version_id, target_sheet
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


def build_eulr_bqml_training_ddl(project_id: str, dataset_id: str) -> list[str]:
    """Build BigQuery ML ARIMA_PLUS DDL statements for Macro, Crudes, and Tanker Freight."""
    proj = validate_bq_identifier(project_id)
    dset = validate_bq_identifier(dataset_id)
    fq = f"`{proj}.{dset}"

    statements: list[str] = []
    for domain, model_suffix in (
        ("MACRO", "bqml_eulr_macro"),
        ("CRUDES", "bqml_eulr_crudes"),
        ("FREIGHT", "bqml_eulr_freight"),
    ):
        statements.append(
            f"""
            CREATE OR REPLACE MODEL {fq}.{model_suffix}`
            OPTIONS(
              MODEL_TYPE = 'ARIMA_PLUS',
              TIME_SERIES_TIMESTAMP_COL = 'series_date',
              TIME_SERIES_DATA_COL = 'actual_value',
              TIME_SERIES_ID_COL = 'series_id',
              DATA_FREQUENCY = 'YEARLY',
              HORIZON = 30,
              AUTO_ARIMA = TRUE,
              DECOMPOSE_TIME_SERIES = TRUE
            ) AS
            SELECT series_date, series_id, actual_value
            FROM {fq}.dt_driver_trajectories`
            WHERE domain_group = '{domain}'
            """
        )

    statements.append(
        f"""
        CREATE OR REPLACE VIEW {fq}.vw_eulr_bqml_forecasts` AS
        WITH raw_fc AS (
          SELECT 'MACRO' AS domain_group, series_id, EXTRACT(YEAR FROM forecast_timestamp) AS forecast_year,
                 forecast_value, prediction_interval_lower_bound AS lower_bound, prediction_interval_upper_bound AS upper_bound
          FROM ML.FORECAST(MODEL {fq}.bqml_eulr_macro`, STRUCT(26 AS horizon, 0.90 AS confidence_level))
          UNION ALL
          SELECT 'CRUDES' AS domain_group, series_id, EXTRACT(YEAR FROM forecast_timestamp) AS forecast_year,
                 forecast_value, prediction_interval_lower_bound AS lower_bound, prediction_interval_upper_bound AS upper_bound
          FROM ML.FORECAST(MODEL {fq}.bqml_eulr_crudes`, STRUCT(26 AS horizon, 0.90 AS confidence_level))
          UNION ALL
          SELECT 'FREIGHT' AS domain_group, series_id, EXTRACT(YEAR FROM forecast_timestamp) AS forecast_year,
                 forecast_value, prediction_interval_lower_bound AS lower_bound, prediction_interval_upper_bound AS upper_bound
          FROM ML.FORECAST(MODEL {fq}.bqml_eulr_freight`, STRUCT(26 AS horizon, 0.90 AS confidence_level))
        ),
        meta AS (
          SELECT DISTINCT domain_group, series_id, series_label, units, target_sheet, target_row
          FROM {fq}.dt_driver_trajectories`
        )
        SELECT
          r.domain_group,
          r.series_id,
          m.series_label,
          m.units,
          m.target_sheet,
          m.target_row,
          r.forecast_year,
          r.forecast_value,
          r.lower_bound,
          r.upper_bound
        FROM raw_fc r
        JOIN meta m USING (domain_group, series_id)
        WHERE r.forecast_year BETWEEN 2025 AND 2050
        """
    )
    return statements
