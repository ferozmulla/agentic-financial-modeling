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

CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_audit_dashboard_lean` AS
SELECT
  event_id,
  when_event_utc AS event_time_utc,
  CASE
    WHEN workbook_id LIKE 'Regional Power Generation Techno-Economic Model — Brazil v13%' THEN 'Brazil_TT_v13_RJEB (Master)'
    WHEN workbook_id LIKE 'New Copy of%' THEN 'New Copy — Brazil_TT_v13_RJEB'
    WHEN workbook_id LIKE 'FHM Copy of%' THEN 'FHM Copy — Brazil_TT_v13_RJEB'
    ELSE workbook_id
  END AS workbook_name,
  workbook_id AS raw_workbook_id,
  who_spreadsheet_id AS spreadsheet_id,
  sheet_name AS tab_name,
  CASE
    WHEN cell_coord = '#REF!' THEN 'Column / Grid'
    ELSE cell_coord
  END AS cell_ref,
  what_change_type AS change_type_code,
  CASE what_change_type
    WHEN 'MANUAL_OVERRIDE' THEN 'Manual Override'
    WHEN 'FORMULA_MODIFIED' THEN 'Formula Modified'
    WHEN 'SCENARIO_PARAMETER_MODIFIED' THEN 'Parameter Modified'
    WHEN 'HEADER_OR_LABEL_MODIFIED' THEN 'Header / Label Modified'
    WHEN 'ROW_INSERTED' THEN 'Row Inserted'
    WHEN 'ROW_DELETED' THEN 'Row Deleted'
    WHEN 'COL_INSERTED' THEN 'Column Inserted'
    WHEN 'COL_DELETED' THEN 'Column Deleted'
    WHEN 'SHEET_ADDED' THEN 'Sheet Added'
    WHEN 'SHEET_DELETED' THEN 'Sheet Deleted'
    WHEN 'SHEET_VISIBILITY_CHANGED' THEN 'Sheet Visibility Changed'
    ELSE INITCAP(REPLACE(what_change_type, '_', ' '))
  END AS change_type_label,
  CASE what_semantic_role
    WHEN 'FORMULA_CELL' THEN 'Formula Cell'
    WHEN 'LABEL_OR_STATIC_CELL' THEN 'Static / Label'
    WHEN 'SCENARIO_INPUT' THEN 'Scenario Input'
    WHEN 'SOLVER_OUTPUT' THEN 'Solver Output'
    ELSE INITCAP(REPLACE(what_semantic_role, '_', ' '))
  END AS cell_role_label,
  severity AS risk_level,
  COALESCE(
    NULLIF(JSON_VALUE(before_state, '$.formula'), ''),
    NULLIF(JSON_VALUE(before_state, '$.value'), ''),
    '—'
  ) AS before_display,
  COALESCE(
    NULLIF(JSON_VALUE(after_state, '$.formula'), ''),
    NULLIF(JSON_VALUE(after_state, '$.value'), ''),
    '—'
  ) AS after_display,
  CONCAT(
    COALESCE(NULLIF(JSON_VALUE(before_state, '$.formula'), ''), NULLIF(JSON_VALUE(before_state, '$.value'), ''), '—'),
    ' → ',
    COALESCE(NULLIF(JSON_VALUE(after_state, '$.formula'), ''), NULLIF(JSON_VALUE(after_state, '$.value'), ''), '—')
  ) AS change_summary,
  who_google_user AS analyst_email,
  SPLIT(who_google_user, '@')[SAFE_OFFSET(0)] AS analyst_handle
FROM `sheets_commodity_mod_governance.audit_events`
WHERE what_change_type != 'INITIAL_BASELINE_INGESTED'
ORDER BY when_event_utc DESC;

