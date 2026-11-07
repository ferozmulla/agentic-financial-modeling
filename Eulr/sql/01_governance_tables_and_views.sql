-- BigQuery DDL: EULR Governance, SharePoint-Portable Upstream Link Registry, UPLOAD & 4-Ws Audit Tables
-- Project: comm-model-mod | Dataset: eulr_commodity_mod_governance

CREATE TABLE IF NOT EXISTS `comm-model-mod.eulr_commodity_mod_governance.upstream_external_series` (
  vintage_tag STRING NOT NULL,
  link_health_tier STRING NOT NULL,
  external_link_idx STRING NOT NULL,
  sharepoint_url STRING,
  external_workbook_name STRING NOT NULL,
  source_sheet STRING NOT NULL,
  source_cell_a1 STRING NOT NULL,
  target_eulr_sheet STRING NOT NULL,
  target_cell_a1 STRING NOT NULL,
  baseline_cached_value FLOAT64,
  active_value FLOAT64,
  value_source STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE OR REPLACE VIEW `comm-model-mod.eulr_commodity_mod_governance.vw_upstream_links_health` AS
SELECT
  vintage_tag,
  link_health_tier,
  external_link_idx,
  external_workbook_name,
  sharepoint_url,
  source_sheet,
  source_cell_a1,
  target_eulr_sheet,
  target_cell_a1,
  baseline_cached_value,
  active_value,
  ROUND(active_value - baseline_cached_value, 6) AS peer_delta,
  value_source,
  updated_at
FROM `comm-model-mod.eulr_commodity_mod_governance.upstream_external_series`;

CREATE TABLE IF NOT EXISTS `comm-model-mod.eulr_commodity_mod_governance.eulr_upload_series` (
  vintage_tag STRING NOT NULL,
  row_idx INT64 NOT NULL,
  series_mnemonic STRING NOT NULL,
  description STRING,
  unit STRING,
  value_2024 FLOAT64,
  value_2025 FLOAT64,
  value_2030 FLOAT64,
  value_2050 FLOAT64,
  published_at TIMESTAMP NOT NULL
);

CREATE OR REPLACE VIEW `comm-model-mod.eulr_commodity_mod_governance.vw_eulr_upload_latest` AS
SELECT
  vintage_tag,
  row_idx,
  series_mnemonic,
  description,
  unit,
  value_2024,
  value_2025,
  value_2030,
  value_2050,
  published_at
FROM `comm-model-mod.eulr_commodity_mod_governance.eulr_upload_series`
ORDER BY row_idx ASC;

CREATE TABLE IF NOT EXISTS `comm-model-mod.eulr_commodity_mod_governance.eulr_links_out` (
  vintage_tag STRING NOT NULL,
  row_idx INT64 NOT NULL,
  series_mnemonic STRING NOT NULL,
  description STRING,
  unit STRING,
  value_2024 FLOAT64,
  value_2025 FLOAT64,
  value_2030 FLOAT64,
  value_2050 FLOAT64,
  published_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `comm-model-mod.eulr_commodity_mod_governance.audit_events` (
  event_id STRING NOT NULL,
  when_event_utc TIMESTAMP NOT NULL,
  who_actor_email STRING NOT NULL,
  where_spreadsheet_id STRING NOT NULL,
  copy_location_url STRING,
  where_sheet_name STRING NOT NULL,
  where_cell_a1 STRING NOT NULL,
  what_classification STRING NOT NULL,
  before_value STRING,
  new_value STRING,
  before_formula STRING,
  new_formula STRING,
  why_ai_summary STRING,
  rollback_tier_hint STRING
);

CREATE OR REPLACE VIEW `comm-model-mod.eulr_commodity_mod_governance.vw_audit_4w_summary` AS
SELECT
  event_id,
  when_event_utc,
  who_actor_email,
  where_spreadsheet_id,
  copy_location_url,
  where_sheet_name,
  where_cell_a1,
  what_classification,
  before_value,
  new_value,
  before_formula,
  new_formula,
  why_ai_summary,
  rollback_tier_hint
FROM `comm-model-mod.eulr_commodity_mod_governance.audit_events`
ORDER BY when_event_utc DESC;
