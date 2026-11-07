- dashboard: metadata_governance
  title: "Model: Brazil_TT_v13_RJEB — 4-Ws Metadata Governance"
  layout: newspaper
  preferred_viewer: dashboards-next
  description: "Coach-styled LookML Governance Dashboard for consuming BigQuery metadata changes across Master and Analyst Google Sheet copies."

  filters:
  - name: timeframe_window
    title: "Timeframe"
    type: field_filter
    default_value: "30 days"
    allow_multiple_values: false
    required: false
    ui_config:
      type: button_toggles
      display: inline
      options:
      - "1 hour"
      - "24 hours"
      - "7 days"
      - "30 days"
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    field: vw_audit_dashboard_lean.event_time_utc_time

  - name: master_sheet_name
    title: "Master Sheet / Copy"
    type: field_filter
    default_value: ""
    allow_multiple_values: true
    required: false
    ui_config:
      type: dropdown_menu
      display: inline
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    field: vw_audit_dashboard_lean.workbook_name

  - name: user_name
    title: "Analyst"
    type: field_filter
    default_value: ""
    allow_multiple_values: true
    required: false
    ui_config:
      type: dropdown_menu
      display: inline
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    field: vw_audit_dashboard_lean.analyst_email

  elements:
  - title: "Total Modifications"
    name: kpi_total_modifications
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: single_value
    fields: [vw_audit_dashboard_lean.total_modifications]
    custom_color_enabled: true
    custom_color: "#1E3A8A"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 0
    col: 0
    width: 6
    height: 3

  - title: "Critical Formula Overrides"
    name: kpi_critical_overrides
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: single_value
    fields: [vw_audit_dashboard_lean.critical_override_count]
    custom_color_enabled: true
    custom_color: "#B91C1C"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 0
    col: 6
    width: 6
    height: 3

  - title: "Active Workbooks"
    name: kpi_active_workbooks
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: single_value
    fields: [vw_audit_dashboard_lean.distinct_workbooks]
    custom_color_enabled: true
    custom_color: "#53389E"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 0
    col: 12
    width: 6
    height: 3

  - title: "Active Analysts"
    name: kpi_active_analysts
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: single_value
    fields: [vw_audit_dashboard_lean.distinct_analysts]
    custom_color_enabled: true
    custom_color: "#146C43"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 0
    col: 18
    width: 6
    height: 3

  - title: "Most Modified Sheets (Tabs)"
    name: chart_most_modified_sheets
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: looker_bar
    fields: [vw_audit_dashboard_lean.tab_name, vw_audit_dashboard_lean.total_modifications]
    sorts: [vw_audit_dashboard_lean.total_modifications desc]
    color_application:
      collection_id: legacy
      custom:
        id: coach-pastel-periwinkle
        label: "Coach Pastel Periwinkle"
        type: discrete
        colors:
        - "#8EB5F0"
        - "#CADCFA"
        - "#EBE5F8"
        - "#E2F3EB"
        - "#F9EBD2"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 3
    col: 0
    width: 8
    height: 6

  - title: "Modifications by Change Type"
    name: chart_modifications_by_type
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: looker_bar
    fields: [vw_audit_dashboard_lean.change_type_label, vw_audit_dashboard_lean.total_modifications]
    sorts: [vw_audit_dashboard_lean.total_modifications desc]
    color_application:
      collection_id: legacy
      custom:
        id: coach-pastel-semantic
        label: "Coach Pastel Semantic"
        type: discrete
        colors:
        - "#E89F9E"
        - "#F3C892"
        - "#C5B4E3"
        - "#9ED5B8"
        - "#8EB5F0"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 3
    col: 8
    width: 8
    height: 6

  - title: "Workbook Copy Drift Comparison"
    name: chart_workbook_drift_comparison
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: looker_bar
    fields: [vw_audit_dashboard_lean.workbook_name, vw_audit_dashboard_lean.critical_override_count, vw_audit_dashboard_lean.structural_or_label_count]
    sorts: [vw_audit_dashboard_lean.critical_override_count desc]
    stacking: normal
    color_application:
      collection_id: legacy
      custom:
        id: coach-drift-split
        label: "Coach Drift Split"
        type: discrete
        colors:
        - "#E89F9E"
        - "#8EB5F0"
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 3
    col: 16
    width: 8
    height: 6

  - title: "4-Ws Metadata Audit Trail"
    name: table_lean_audit_summary
    model: commodity_governance
    explore: vw_audit_dashboard_lean
    type: looker_grid
    fields: [
      vw_audit_dashboard_lean.event_time_utc_time,
      vw_audit_dashboard_lean.workbook_name,
      vw_audit_dashboard_lean.tab_name,
      vw_audit_dashboard_lean.cell_ref,
      vw_audit_dashboard_lean.change_type_label,
      vw_audit_dashboard_lean.cell_role_label,
      vw_audit_dashboard_lean.risk_level,
      vw_audit_dashboard_lean.change_summary,
      vw_audit_dashboard_lean.analyst_email
    ]
    sorts: [vw_audit_dashboard_lean.event_time_utc_time desc]
    limit: 200
    listen:
      timeframe_window: vw_audit_dashboard_lean.event_time_utc_time
      master_sheet_name: vw_audit_dashboard_lean.workbook_name
      user_name: vw_audit_dashboard_lean.analyst_email
    row: 9
    col: 0
    width: 24
    height: 10
