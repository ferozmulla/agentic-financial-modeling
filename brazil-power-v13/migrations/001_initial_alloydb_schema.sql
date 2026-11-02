-- 001_initial_alloydb_schema.sql
-- DDL for the 10 AlloyDB for PostgreSQL / PostgreSQL 15 Governance, AST, DAG & Telemetry Tables

CREATE TABLE IF NOT EXISTS workbooks (
    workbook_id VARCHAR(128) PRIMARY KEY,
    spreadsheet_id VARCHAR(128) NOT NULL UNIQUE,
    workbook_name VARCHAR(256) NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    latest_version_id VARCHAR(64),
    latest_version_seq_num INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workbook_versions (
    version_id VARCHAR(64) PRIMARY KEY,
    workbook_id VARCHAR(128) NOT NULL REFERENCES workbooks(workbook_id),
    spreadsheet_id VARCHAR(128) NOT NULL,
    parent_version_id VARCHAR(64),
    version_seq_num INTEGER NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    gcs_snapshot_uri TEXT NOT NULL,
    committed_by_google_user VARCHAR(256) NOT NULL,
    committed_by_iam_principal VARCHAR(256) NOT NULL,
    commit_comment TEXT,
    total_sheets INTEGER NOT NULL,
    total_populated_cells INTEGER NOT NULL,
    total_formula_cells INTEGER NOT NULL,
    total_dag_edges INTEGER NOT NULL,
    structural_mutation_count INTEGER NOT NULL DEFAULT 0,
    manual_override_count INTEGER NOT NULL DEFAULT 0,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workbook_versions_sheet_seq
    ON workbook_versions(spreadsheet_id, version_seq_num DESC);

CREATE TABLE IF NOT EXISTS worksheets (
    worksheet_id VARCHAR(96) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES workbook_versions(version_id),
    sheet_index INTEGER NOT NULL,
    sheet_name VARCHAR(128) NOT NULL,
    visibility VARCHAR(32) NOT NULL DEFAULT 'visible',
    populated_cell_count INTEGER NOT NULL,
    formula_cell_count INTEGER NOT NULL,
    shared_formula_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cells (
    cell_id VARCHAR(128) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES workbook_versions(version_id),
    sheet_name VARCHAR(128) NOT NULL,
    cell_coord VARCHAR(24) NOT NULL,
    row_num INTEGER NOT NULL,
    col_num INTEGER NOT NULL,
    col_letter VARCHAR(8) NOT NULL,
    data_type VARCHAR(16) NOT NULL,
    raw_value TEXT,
    numeric_value DOUBLE PRECISION,
    raw_formula TEXT,
    canonical_formula TEXT,
    r1c1_formula TEXT,
    formula_hash VARCHAR(64),
    shared_group_index INTEGER,
    is_shared_master BOOLEAN NOT NULL DEFAULT FALSE,
    semantic_role VARCHAR(32) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cells_version_sheet_coord
    ON cells(version_id, sheet_name, cell_coord);

CREATE TABLE IF NOT EXISTS cell_dependency_edges (
    edge_id VARCHAR(128) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES workbook_versions(version_id),
    precedent_sheet VARCHAR(128) NOT NULL,
    precedent_coord VARCHAR(24) NOT NULL,
    dependent_sheet VARCHAR(128) NOT NULL,
    dependent_coord VARCHAR(24) NOT NULL,
    reference_type VARCHAR(32) NOT NULL DEFAULT 'DIRECT_CELL'
);

CREATE INDEX IF NOT EXISTS idx_dag_precedent
    ON cell_dependency_edges(version_id, precedent_sheet, precedent_coord);
CREATE INDEX IF NOT EXISTS idx_dag_dependent
    ON cell_dependency_edges(version_id, dependent_sheet, dependent_coord);

CREATE TABLE IF NOT EXISTS named_ranges (
    named_range_id VARCHAR(128) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES workbook_versions(version_id),
    name VARCHAR(256) NOT NULL,
    local_sheet_id INTEGER,
    scope_sheet_name VARCHAR(128),
    refers_to TEXT NOT NULL,
    is_broken_ref BOOLEAN NOT NULL DEFAULT FALSE,
    hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS macro_bindings (
    binding_id VARCHAR(128) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES workbook_versions(version_id),
    sheet_name VARCHAR(128) NOT NULL,
    anchor_cell VARCHAR(24) NOT NULL,
    button_label VARCHAR(256) NOT NULL,
    macro_target VARCHAR(128) NOT NULL,
    raw_macro_ref VARCHAR(256) NOT NULL
);

CREATE TABLE IF NOT EXISTS technical_debt_items (
    debt_id VARCHAR(128) PRIMARY KEY,
    version_id VARCHAR(64) NOT NULL REFERENCES workbook_versions(version_id),
    debt_category VARCHAR(64) NOT NULL,
    identifier VARCHAR(256) NOT NULL,
    location VARCHAR(256) NOT NULL,
    details TEXT NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'WARNING'
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id VARCHAR(64) PRIMARY KEY,
    workbook_id VARCHAR(128) NOT NULL,
    spreadsheet_id VARCHAR(128) NOT NULL,
    version_id VARCHAR(64),
    parent_version_id VARCHAR(64),
    version_seq_num INTEGER NOT NULL DEFAULT 1,
    sheet_name VARCHAR(128) NOT NULL,
    cell_coord VARCHAR(32) NOT NULL,
    what_element_coord VARCHAR(256) NOT NULL,
    what_semantic_role VARCHAR(32) NOT NULL,
    what_change_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    who_google_user VARCHAR(256) NOT NULL,
    who_iam_principal VARCHAR(256) NOT NULL,
    who_client_platform VARCHAR(128) NOT NULL,
    who_spreadsheet_id VARCHAR(128) NOT NULL,
    when_event_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    gcs_snapshot_uri TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_events_spreadsheet_when
    ON audit_events(spreadsheet_id, when_event_utc DESC);

CREATE TABLE IF NOT EXISTS solver_run_telemetry (
    run_id VARCHAR(64) PRIMARY KEY,
    spreadsheet_id VARCHAR(128) NOT NULL,
    workbook_id VARCHAR(128) NOT NULL,
    macro_name VARCHAR(64) NOT NULL,
    caller_google_user VARCHAR(256) NOT NULL,
    solve_count INTEGER NOT NULL,
    execution_time_ms DOUBLE PRECISION NOT NULL,
    execution_engine VARCHAR(64) NOT NULL,
    parity_mode VARCHAR(32) NOT NULL,
    executed_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
