#!/usr/bin/env python3
"""Deploy isolated `model-onboarding-mcp` to Google Cloud Run using a clean minimal source bundle."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_clean_pkg(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        ".ruff_cache",
        ".DS_Store",
        "*.xlsx",
        "*.xlsm",
        "*.csv",
        "reports",
        "Portfolio scoring reports*",
    )
    shutil.copytree(src, dst, ignore=ignore)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy model-onboarding-mcp to Google Cloud Run.")
    parser.add_argument("--project-id", default="comm-model-mod")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--service-name", default="model-onboarding-mcp")
    parser.add_argument("--service-account", default="sa-model-onboarding@comm-model-mod.iam.gserviceaccount.com")
    parser.add_argument("--staging-bucket", default="comm-model-mod-onboarding-staging")
    parser.add_argument("--vault-bucket", default="comm-model-mod-onboarding-staging")
    parser.add_argument("--github-repo", default="ferozmulla/agentic-financial-modeling")
    args = parser.parse_args()

    env = dict(os.environ)
    existing_metrics = env.get("CLOUDSDK_METRICS_ENVIRONMENT", "").strip()
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = (
        f"{existing_metrics} datacloud.antigravity".strip()
        if "datacloud." not in existing_metrics
        else existing_metrics
    )

    image_uri = (
        f"{args.region}-docker.pkg.dev/{args.project_id}/cloud-run-source-deploy/{args.service_name}:latest"
    )

    with tempfile.TemporaryDirectory(prefix="deploy_onboard_mcp_") as tmp_ctx:
        ctx_dir = Path(tmp_ctx)
        _copy_clean_pkg(REPO_ROOT / "portfolio-assessment", ctx_dir / "portfolio-assessment")
        _copy_clean_pkg(REPO_ROOT / "model-onboarding", ctx_dir / "model-onboarding")
        shutil.copy2(REPO_ROOT / "model-onboarding" / "Dockerfile", ctx_dir / "Dockerfile")

        build_cmd = [
            "gcloud",
            "builds",
            "submit",
            str(ctx_dir),
            "--project",
            args.project_id,
            "--tag",
            image_uri,
            "--quiet",
        ]
        b_proc = subprocess.run(build_cmd, env=env, check=False)
        if b_proc.returncode != 0:
            return b_proc.returncode

    deploy_cmd = [
        "gcloud",
        "run",
        "deploy",
        args.service_name,
        "--image",
        image_uri,
        "--project",
        args.project_id,
        "--region",
        args.region,
        "--service-account",
        args.service_account,
        "--allow-unauthenticated",
        "--memory",
        "1Gi",
        "--timeout",
        "900",
        "--labels",
        "datacloud=antigravity,component=model-onboarding-mcp",
        "--set-env-vars",
        (
            f"ONBOARD_GCP_PROJECT_ID={args.project_id},"
            f"ONBOARD_GCP_REGION={args.region},"
            f"ONBOARD_STAGING_BUCKET={args.staging_bucket},"
            f"ONBOARD_VAULT_BUCKET={args.vault_bucket},"
            f"ONBOARD_GITHUB_REPO={args.github_repo},"
            f"ONBOARD_SERVICE_ACCOUNT_EMAIL={args.service_account}"
        ),
        "--quiet",
    ]
    d_proc = subprocess.run(deploy_cmd, env=env, check=False)
    return d_proc.returncode


if __name__ == "__main__":
    sys.exit(main())
