-- 001_dataset_and_tables.sql
-- BigQuery Dataset (Location: us-central1) and Partitioned/Clustered Governance & Telemetry Tables

CREATE SCHEMA IF NOT EXISTS `sheets_commodity_mod_governance`
OPTIONS (
  location = 'us-central1',
  description = 'Enterprise Commodity Modeling — Google Sheets Modernization & 4-Ws Structural Governance Dataset'
);

CREATE TABLE IF NOT EXISTS `sheets_commodity_mod_governance.audit_events` (
  event_id STRING NOT NULL,
  workbook_id STRING NOT NULL,
  spreadsheet_id STRING NOT NULL,
  version_id STRING,
  parent_version_id STRING,
  version_seq_num INT64 NOT NULL,
  sheet_name STRING NOT NULL,
  cell_coord STRING NOT NULL,
  what_element_coord STRING NOT NULL,
  what_semantic_role STRING NOT NULL,
  what_change_type STRING NOT NULL,
  severity STRING NOT NULL,
  before_state JSON,
  after_state JSON,
  who_google_user STRING NOT NULL,
  who_iam_principal STRING NOT NULL,
  who_client_platform STRING NOT NULL,
  who_spreadsheet_id STRING NOT NULL,
  when_event_utc TIMESTAMP NOT NULL,
  gcs_snapshot_uri STRING NOT NULL
)
PARTITION BY DATE(when_event_utc)
CLUSTER BY spreadsheet_id, what_change_type, severity, sheet_name;

CREATE TABLE IF NOT EXISTS `sheets_commodity_mod_governance.solver_run_telemetry` (
  run_id STRING NOT NULL,
  spreadsheet_id STRING NOT NULL,
  workbook_id STRING NOT NULL,
  macro_name STRING NOT NULL,
  caller_google_user STRING NOT NULL,
  solve_count INT64 NOT NULL,
  execution_time_ms FLOAT64 NOT NULL,
  execution_engine STRING NOT NULL,
  parity_mode STRING NOT NULL,
  executed_at_utc TIMESTAMP NOT NULL
)
PARTITION BY DATE(executed_at_utc)
CLUSTER BY macro_name, spreadsheet_id;

CREATE TABLE IF NOT EXISTS `sheets_commodity_mod_governance.historical_lt_trajectories` (
  forecast_year_date DATE NOT NULL,
  curve_family STRING NOT NULL,
  technology_code STRING NOT NULL,
  trajectory_value FLOAT64 NOT NULL
);

CREATE TABLE IF NOT EXISTS `sheets_commodity_mod_governance.solver_training_grid` (
  technology_code STRING NOT NULL,
  capex_multiplier FLOAT64 NOT NULL,
  fuel_cost_multiplier FLOAT64 NOT NULL,
  capacity_factor_multiplier FLOAT64 NOT NULL,
  wacc_rate FLOAT64 NOT NULL,
  economic_life_yrs INT64 NOT NULL,
  solved_lcoe FLOAT64 NOT NULL
);
