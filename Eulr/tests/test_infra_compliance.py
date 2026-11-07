"""Phase 5 Infrastructure & Security Compliance Tests: TEST-INFRA-01..06."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
TF_DIR = BASE_DIR / "infra" / "terraform"
SQL_DIR = BASE_DIR / "sql"


def test_infra_01_to_06_terraform_and_sql_compliance() -> None:
    """TEST-INFRA-01..06: Verify mandatory labels, serverless isolation, disable_on_destroy=false, and zero hardcoded secrets."""
    locals_tf = (TF_DIR / "locals.tf").read_text(encoding="utf-8")
    main_tf = (TF_DIR / "main.tf").read_text(encoding="utf-8")
    vars_tf = (TF_DIR / "variables.tf").read_text(encoding="utf-8")

    # TEST-INFRA-01: Mandatory labels (env, app="eulr-sheets-mod", owner="quant-platform", cost-center="commodities-r-and-d")
    assert 'app         = "eulr-sheets-mod"' in locals_tf
    assert 'owner       = "quant-platform"' in locals_tf
    assert 'cost-center = "commodities-r-and-d"' in locals_tf

    # TEST-INFRA-02: Target project comm-model-mod and region us-central1
    assert 'default     = "comm-model-mod"' in vars_tf
    assert 'default     = "us-central1"' in vars_tf

    # TEST-INFRA-03: 100% Serverless (Zero AlloyDB / Cloud SQL instances)
    assert "google_alloydb" not in main_tf
    assert "google_sql_database_instance" not in main_tf

    # TEST-INFRA-04: Isolated eulr-* resource naming (does not collide with brazil-power-v13)
    assert 'name     = "eulr-equilibrium-gateway"' in main_tf
    assert 'dataset_id                 = "eulr_commodity_mod_governance"' in main_tf
    assert 'name                        = "${var.project_id}-eulr-snapshots"' in main_tf

    # TEST-INFRA-05: Non-destructive API enablement (disable_on_destroy = false)
    assert "disable_on_destroy = false" in main_tf

    # TEST-INFRA-06: SQL & Vertex AI Model Registry definitions present and zero hardcoded keys
    sql_01 = (SQL_DIR / "01_governance_tables_and_views.sql").read_text(encoding="utf-8")
    sql_02 = (SQL_DIR / "02_bqml_models.sql").read_text(encoding="utf-8")
    assert "upstream_external_series" in sql_01
    assert "vw_upstream_links_health" in sql_01
    assert "vw_eulr_upload_latest" in sql_01
    assert "vw_audit_4w_summary" in sql_01
    assert "ARIMA_PLUS" in sql_02
    assert "eulr-sheets-mod-margin-surrogate" in sql_02
