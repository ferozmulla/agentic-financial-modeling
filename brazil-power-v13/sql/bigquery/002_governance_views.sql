-- 002_governance_views.sql
-- Native Connected Sheets for BigQuery Governance Views (4-Ws Summary, Manual Overrides, Solver SLA)

CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_audit_4w_summary` AS
SELECT
  event_id,
  workbook_id AS copy_name,
  version_seq_num,
  sheet_name,
  cell_coord,
  what_element_coord,
  what_semantic_role,
  what_change_type,
  severity,
  JSON_VALUE(before_state, '$.formula') AS before_formula,
  JSON_VALUE(before_state, '$.value') AS before_value,
  JSON_VALUE(after_state, '$.formula') AS after_formula,
  JSON_VALUE(after_state, '$.value') AS after_value,
  who_google_user,
  who_iam_principal,
  who_client_platform,
  who_spreadsheet_id,
  when_event_utc,
  gcs_snapshot_uri AS copy_location_url
FROM `sheets_commodity_mod_governance.audit_events`
ORDER BY when_event_utc DESC;

CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_manual_overrides` AS
SELECT
  event_id,
  workbook_id AS copy_name,
  version_seq_num,
  sheet_name,
  cell_coord,
  what_element_coord,
  JSON_VALUE(before_state, '$.formula') AS overwritten_formula,
  JSON_VALUE(after_state, '$.value') AS hardcoded_literal_value,
  who_google_user,
  who_client_platform,
  who_spreadsheet_id,
  when_event_utc,
  gcs_snapshot_uri AS copy_location_url
FROM `sheets_commodity_mod_governance.audit_events`
WHERE what_change_type = 'MANUAL_OVERRIDE'
ORDER BY when_event_utc DESC;

CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_solver_performance_sla` AS
SELECT
  macro_name,
  COUNT(*) AS total_invocations,
  AVG(solve_count) AS avg_solves_per_call,
  ROUND(AVG(execution_time_ms), 2) AS avg_latency_ms,
  ROUND(APPROX_QUANTILES(execution_time_ms, 100)[OFFSET(95)], 2) AS p95_latency_ms,
  MAX(executed_at_utc) AS last_executed_utc
FROM `sheets_commodity_mod_governance.solver_run_telemetry`
GROUP BY macro_name
ORDER BY p95_latency_ms DESC;
