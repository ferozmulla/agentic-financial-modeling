"""End-to-end tests for `OnboardingController` and `pr_publisher` using an isolated temporary Git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import openpyxl

from model_onboarding.config import OnboardingSettings
from model_onboarding.controller import OnboardingController
from model_onboarding.models import (
    HygieneGateReport,
    OnboardingJobState,
    ParitySheetSummary,
    ParityVerificationReport,
)
from tests.test_sandbox_worker_and_sanitizer import _build_valid_generated_twin, _make_seed_xlsx


class _StubSandboxWorker:
    """Deterministic stub implementing `CodegenSandboxWorker` for offline controller testing."""

    def generate_and_verify_twin(
        self,
        job_id: str,
        xlsx_path: Path,
        hygiene_report: HygieneGateReport,
        work_dir: Path,
    ) -> tuple[Path, ParityVerificationReport]:
        del job_id, xlsx_path
        pkg_dir = _build_valid_generated_twin(
            work_dir / f"{hygiene_report.model_slug}-bq-twin",
            slug=hygiene_report.model_slug,
        )
        parity = ParityVerificationReport(
            model_slug=hygiene_report.model_slug,
            passed=True,
            pytest_passed=3,
            pytest_failed=0,
            total_compared_cells=120,
            total_matched_cells=120,
            parity_rate_pct=100.0,
            max_abs_error=1e-7,
            max_rel_error=1e-7,
            sheet_summaries=[
                ParitySheetSummary(
                    sheet_name="Model",
                    compared_cells=120,
                    matched_cells=120,
                    mismatched_cells=0,
                    max_abs_error=1e-7,
                    max_rel_error=1e-7,
                )
            ],
            interaction_id="int_stub_42",
            environment_id="env_stub_42",
            verified_locally=True,
        )
        return pkg_dir, parity


def _init_temp_git_repo(repo_dir: Path) -> Path:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initial"], cwd=repo_dir, check=True, capture_output=True)
    return repo_dir


def test_controller_end_to_end_creates_clean_local_onboarding_branch(tmp_path: Path) -> None:
    repo = _init_temp_git_repo(tmp_path / "repo")
    seed = _make_seed_xlsx(tmp_path / "Wind_Portfolio_2026.xlsx")

    settings = OnboardingSettings(local_jobs_dir=tmp_path / "jobs")
    ctrl = OnboardingController(
        repo_root=repo,
        settings=settings,
        sandbox_worker=_StubSandboxWorker(),
    )

    pending = ctrl.create_pending_job(str(seed), model_slug="wind-portfolio")
    done = ctrl.execute_job(pending.job_id, local_branch_only=True)

    assert done.state == OnboardingJobState.AWAITING_PR_APPROVAL
    assert done.pr_result is not None
    assert done.pr_result.branch_name.startswith("onboard/wind-portfolio-")
    assert done.pr_result.local_only is True

    # Verify main working tree remained completely untouched while the onboarding branch has the package + reports
    active_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert active_branch == "main"
    assert not (repo / "wind-portfolio-bq-twin").exists()

    tree_files = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", done.pr_result.branch_name],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "wind-portfolio-bq-twin/Dockerfile" in tree_files
    assert "wind-portfolio-bq-twin/reports/hygiene_exception_report.md" in tree_files
    assert "wind-portfolio-bq-twin/reports/parity_verification_report.md" in tree_files
    assert not any(f.endswith((".xlsx", ".xlsm")) for f in tree_files)


def test_controller_blocks_no_go_unless_force_override(tmp_path: Path) -> None:
    repo = _init_temp_git_repo(tmp_path / "repo2")
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws["A1"] = 123.0  # Zero formulas -> NO_GO
    no_go_xlsx = tmp_path / "NoFormulas.xlsx"
    wb.save(no_go_xlsx)

    settings = OnboardingSettings(local_jobs_dir=tmp_path / "jobs2")
    ctrl = OnboardingController(
        repo_root=repo,
        settings=settings,
        sandbox_worker=_StubSandboxWorker(),
    )

    job1 = ctrl.create_pending_job(str(no_go_xlsx), model_slug="no-formulas")
    blocked = ctrl.execute_job(job1.job_id, force_override=False, local_branch_only=True)
    assert blocked.state == OnboardingJobState.BLOCKED_NO_GO

    # With force_override=True, Administrator explicitly overrides NO_GO and generates branch
    job2 = ctrl.create_pending_job(str(no_go_xlsx), model_slug="no-formulas")
    forced = ctrl.execute_job(job2.job_id, force_override=True, local_branch_only=True)
    assert forced.state == OnboardingJobState.AWAITING_PR_APPROVAL
