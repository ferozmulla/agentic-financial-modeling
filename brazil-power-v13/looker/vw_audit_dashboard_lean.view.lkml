view: vw_audit_dashboard_lean {
  sql_table_name: `comm-model-mod.sheets_commodity_mod_governance.vw_audit_dashboard_lean` ;;
  drill_fields: [event_time_utc_time, workbook_name, tab_name, cell_ref, change_type_label, cell_role_label, risk_level, change_summary, analyst_email]

  dimension: event_id {
    primary_key: yes
    hidden: yes
    type: string
    sql: ${TABLE}.event_id ;;
  }

  dimension_group: event_time_utc {
    label: "Time (UTC)"
    type: time
    timeframes: [raw, time, minute, hour, date, week, month, year]
    sql: ${TABLE}.event_time_utc ;;
  }

  dimension: workbook_name {
    label: "Workbook"
    type: string
    sql: ${TABLE}.workbook_name ;;
  }

  dimension: tab_name {
    label: "Tab"
    type: string
    sql: ${TABLE}.tab_name ;;
  }

  dimension: cell_ref {
    label: "Cell"
    type: string
    sql: ${TABLE}.cell_ref ;;
  }

  dimension: change_type_label {
    label: "Change Type"
    type: string
    sql: ${TABLE}.change_type_label ;;
  }

  dimension: cell_role_label {
    label: "Role"
    type: string
    sql: ${TABLE}.cell_role_label ;;
  }

  dimension: risk_level {
    label: "Severity"
    type: string
    sql: ${TABLE}.risk_level ;;
  }

  dimension: change_summary {
    label: "Before → After"
    type: string
    sql: ${TABLE}.change_summary ;;
  }

  dimension: analyst_email {
    label: "Analyst"
    type: string
    sql: ${TABLE}.analyst_email ;;
  }

  dimension: analyst_handle {
    label: "Analyst Handle"
    type: string
    sql: ${TABLE}.analyst_handle ;;
  }

  measure: total_modifications {
    label: "Total Modifications"
    type: count
  }

  measure: critical_override_count {
    label: "Critical Overrides"
    type: count
    filters: [risk_level: "CRITICAL"]
  }

  measure: structural_or_label_count {
    label: "Structural & Label Edits"
    type: count
    filters: [risk_level: "-CRITICAL"]
  }

  measure: distinct_workbooks {
    label: "Active Workbooks"
    type: count_distinct
    sql: ${workbook_name} ;;
  }

  measure: distinct_analysts {
    label: "Active Analysts"
    type: count_distinct
    sql: ${analyst_email} ;;
  }
}
