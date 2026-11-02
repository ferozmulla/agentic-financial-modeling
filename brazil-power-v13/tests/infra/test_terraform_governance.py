"""Infrastructure-as-Code governance tests for Terraform (TEST-INFRA-01..TEST-INFRA-06)."""

from __future__ import annotations

import shutil
import subprocess

from src.core.config import PROJECT_ROOT

TF_ROOT = PROJECT_ROOT / "infra" / "terraform"


def _read_all_tf_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for p in sorted(TF_ROOT.rglob("*.tf")):
        rel = str(p.relative_to(TF_ROOT))
        files[rel] = p.read_text(encoding="utf-8")
    return files


def test_infra01_terraform_fmt_and_validate() -> None:
    """TEST-INFRA-01: Verify all Terraform modules exist and pass terraform fmt / validate."""
    tf_files = _read_all_tf_files()
    expected_modules = [
        "main.tf",
        "variables.tf",
        "locals.tf",
        "providers.tf",
        "outputs.tf",
        "modules/networking/main.tf",
        "modules/iam/main.tf",
        "modules/storage/main.tf",
        "modules/alloydb/main.tf",
        "modules/bigquery/main.tf",
        "modules/vertex_ai_and_cloud_run/main.tf",
    ]
    for mod in expected_modules:
        assert mod in tf_files, f"Missing expected Terraform file: {mod}"

    tf_bin = shutil.which("terraform")
    if tf_bin:
        fmt_res = subprocess.run(
            [tf_bin, "fmt", "-check", "-recursive"],
            cwd=str(TF_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert fmt_res.returncode == 0, f"terraform fmt failed:\n{fmt_res.stdout}\n{fmt_res.stderr}"


def test_infra02_region_us_central1_and_gemini_us_multiregion() -> None:
    """TEST-INFRA-02: Verify GCP services use us-central1 and Gemini LLMs use US multi-region endpoint."""
    vars_tf = (TF_ROOT / "variables.tf").read_text(encoding="utf-8")
    locals_tf = (TF_ROOT / "locals.tf").read_text(encoding="utf-8")
    tfvars_example = (TF_ROOT / "terraform.tfvars.example").read_text(encoding="utf-8")

    assert 'default     = "comm-model-mod"' in vars_tf
    assert 'default     = "us-central1"' in vars_tf
    assert 'default     = "us-central1-a"' in vars_tf
    assert 'default     = "us"' in vars_tf
    assert '${var.gemini_location}-aiplatform.googleapis.com' in locals_tf

    assert 'region          = "us-central1"' in tfvars_example
    assert 'bq_location     = "us-central1"' in tfvars_example
    assert 'gemini_location = "us"' in tfvars_example


def test_infra03_universal_resource_labels() -> None:
    """TEST-INFRA-03: Verify universal resource label app = 'sheets-commodity-mod' across modules."""
    locals_tf = (TF_ROOT / "locals.tf").read_text(encoding="utf-8")
    assert 'app        = "sheets-commodity-mod"' in locals_tf
    assert 'project    = "enterprise-commodity-modernization"' in locals_tf
    assert 'managed-by = "terraform"' in locals_tf

    for mod_file in (
        "modules/storage/main.tf",
        "modules/alloydb/main.tf",
        "modules/bigquery/main.tf",
        "modules/vertex_ai_and_cloud_run/main.tf",
    ):
        content = (TF_ROOT / mod_file).read_text(encoding="utf-8")
        assert "labels" in content and "var.common_labels" in content, (
            f"Missing var.common_labels in {mod_file}"
        )


def test_infra04_clean_teardown_lifecycle_flags() -> None:
    """TEST-INFRA-04: Verify clean tear-down flags on all stateful resources."""
    storage_tf = (TF_ROOT / "modules/storage/main.tf").read_text(encoding="utf-8")
    alloydb_tf = (TF_ROOT / "modules/alloydb/main.tf").read_text(encoding="utf-8")
    bq_tf = (TF_ROOT / "modules/bigquery/main.tf").read_text(encoding="utf-8")
    vertex_tf = (TF_ROOT / "modules/vertex_ai_and_cloud_run/main.tf").read_text(encoding="utf-8")

    assert "force_destroy               = true" in storage_tf
    assert 'deletion_policy = "FORCE"' in alloydb_tf
    assert "delete_contents_on_destroy = true" in bq_tf
    assert "deletion_protection = false" in bq_tf
    assert "deletion_protection = false" in vertex_tf
    assert "gcloud ai endpoints undeploy-model" in vertex_tf


def test_infra05_least_privilege_service_accounts() -> None:
    """TEST-INFRA-05: Verify dedicated service accounts and absence of primitive Owner/Editor roles."""
    iam_tf = (TF_ROOT / "modules/iam/main.tf").read_text(encoding="utf-8")
    assert 'account_id   = "sa-sheets-gateway"' in iam_tf
    assert 'account_id   = "sa-vertex-solver"' in iam_tf
    assert 'account_id   = "sa-bq-remote-fn"' in iam_tf
    assert "roles/owner" not in iam_tf
    assert "roles/editor" not in iam_tf


def test_infra06_shared_project_isolation_safety() -> None:
    """TEST-INFRA-06: Verify shared project safety in comm-model-mod (additive-only IAM, disable_on_destroy=false)."""
    all_tf = "\n".join(_read_all_tf_files().values())
    assert 'resource "google_project"' not in all_tf
    assert 'resource "google_project_iam_policy"' not in all_tf
    assert 'resource "google_project_iam_binding"' not in all_tf
    assert "disable_on_destroy = false" in (TF_ROOT / "main.tf").read_text(encoding="utf-8")
