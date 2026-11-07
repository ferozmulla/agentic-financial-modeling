connection: "comm_model_mod_bigquery"

include: "*.view.lkml"
include: "*.dashboard.lookml"

datagroup: governance_audit_realtime_dg {
  sql_trigger: SELECT MAX(event_time_utc) FROM `comm-model-mod.sheets_commodity_mod_governance.vw_audit_dashboard_lean` ;;
  max_cache_age: "1 minute"
}

persist_with: governance_audit_realtime_dg

explore: vw_audit_dashboard_lean {
  label: "Brazil Power v13 — 4-Ws Metadata Governance"
  description: "Lean business-friendly 4-Ws audit trail of structural and cell-level modifications across Master and Analyst Google Sheet copies."
}
