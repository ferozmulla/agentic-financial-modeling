"""Admin CLI (`onboard`) for Stage 1 Assessment, Stage 2/3 Submission, Job Status, and Post-PR Deployment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from model_onboarding.config import get_onboarding_settings
from model_onboarding.controller import OnboardingController
from model_onboarding.hygiene_gate import write_hygiene_gate_artifacts
from model_onboarding.models import OnboardingJobState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onboard",
        description=(
            "Onboard Energy modeling spreadsheets (.xlsx/.xlsm): "
            "Hygiene Exception Gate, Managed Agent Sandbox Codegen, Git PR Review, and GCP Deployment."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # 1. onboard assess
    p_assess = sub.add_parser(
        "assess",
        help="Run Stage 1 deterministic MES/MDR hygiene scan, Exception Report, and Go/No-Go verdict.",
    )
    p_assess.add_argument("workbook", help="Local .xlsx/.xlsm path or gs://bucket/object URI.")
    p_assess.add_argument("--slug", default=None, help="Optional lowercase kebab-case model slug.")
    p_assess.add_argument(
        "--refs-dir",
        nargs="*",
        type=Path,
        default=[],
        help="Optional peer workbook folder(s) for external link resolution.",
    )
    p_assess.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory to write hygiene_exception_report.{json,md}.",
    )
    p_assess.add_argument("--json", action="store_true", help="Print JSON report to stdout.")

    # 2. onboard submit
    p_submit = sub.add_parser(
        "submit",
        help="Run Stage 1 Hygiene Gate -> Stage 2 Managed Agent Codegen & Parity -> Stage 3a Git Branch/PR.",
    )
    p_submit.add_argument("workbook", help="Local .xlsx/.xlsm path or gs://bucket/object URI.")
    p_submit.add_argument("--slug", default=None, help="Optional lowercase kebab-case model slug.")
    p_submit.add_argument(
        "--refs-dir",
        nargs="*",
        type=Path,
        default=[],
        help="Optional peer workbook folder(s) for external link resolution.",
    )
    p_submit.add_argument(
        "--force",
        action="store_true",
        help="Override a Stage 1 NO_GO decision and proceed to sandbox codegen.",
    )
    p_submit.add_argument(
        "--local-branch-only",
        action="store_true",
        help="Commit to a local onboard/<slug>-<id> branch without pushing or opening a GitHub PR.",
    )

    # 3. onboard status
    p_status = sub.add_parser("status", help="Inspect status of an onboarding job.")
    p_status.add_argument("job_id", help="Onboarding job identifier (e.g. job-a1b2c3d4e5f6).")

    # 4. onboard deploy
    p_deploy = sub.add_parser(
        "deploy",
        help="Stage 3b (Post-PR Review): Seed BigQuery + BQML, deploy Cloud Run MCP, and publish Skills.",
    )
    p_deploy.add_argument("slug", help="Approved model slug (<slug>-bq-twin directory in repo root).")
    p_deploy.add_argument("--skip-bqml", action="store_true", help="Skip BigQuery ML ARIMA_PLUS training.")
    p_deploy.add_argument("--pr-number", type=int, default=None, help="Optional PR number to verify merged.")
    p_deploy.add_argument(
        "--require-merged-pr",
        action="store_true",
        help="Verify via GitHub API that --pr-number is merged before deploying.",
    )
    p_deploy.add_argument(
        "--registry-project-id",
        default=None,
        help="Optional override project ID for Agent Registry skill/MCP publishing.",
    )

    return parser


def main(argv: Sequence[str] | None = None, controller: OnboardingController | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_onboarding_settings()

    if getattr(args, "registry_project_id", None):
        settings = settings.model_copy(update={"registry_project_id": args.registry_project_id})

    ctrl = controller or OnboardingController(settings=settings)

    if args.command == "assess":
        report = ctrl.assess_only(
            source_path_or_gcs_uri=args.workbook,
            model_slug=args.slug,
            reference_roots=list(args.refs_dir),
        )
        if args.output_dir is not None:
            json_path, md_path = write_hygiene_gate_artifacts(report, args.output_dir)
            if not args.json:
                print(f"Wrote Exception Report to {md_path} and {json_path}")

        if args.json:
            print(json.dumps(report.model_dump(mode="json"), indent=2))
        else:
            print(
                f"[{report.decision.value}] {report.workbook_name} -> slug='{report.model_slug}' | "
                f"Archetype={report.archetype} | MES={report.mes_score:.1f}% | "
                f"MDR={report.mdr_score:.1f}% | MRI={report.mri_score:.1f}% | "
                f"Exceptions={len(report.exceptions)}"
            )
            for item in report.decision_rationale:
                print(f"  - {item}")
        return 0

    if args.command == "submit":
        pending = ctrl.create_pending_job(args.workbook, model_slug=args.slug)
        final_status = ctrl.execute_job(
            job_id=pending.job_id,
            force_override=bool(args.force),
            local_branch_only=bool(args.local_branch_only),
            reference_roots=list(args.refs_dir),
        )
        print(json.dumps(final_status.model_dump(mode="json"), indent=2))
        if final_status.state in {OnboardingJobState.BLOCKED_NO_GO, OnboardingJobState.FAILED}:
            return 1
        return 0

    if args.command == "status":
        st = ctrl.get_job_status(args.job_id)
        print(json.dumps(st.model_dump(mode="json"), indent=2))
        return 0

    if args.command == "deploy":
        summary = ctrl.deploy_approved(
            model_slug=args.slug,
            skip_bqml=bool(args.skip_bqml),
            pr_number=args.pr_number,
            require_merged_pr=bool(args.require_merged_pr),
        )
        print(json.dumps(summary.model_dump(mode="json"), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
