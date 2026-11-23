"""Stage 3a: Git Branch & Pull Request Publisher (Local `git worktree` + Repo-Free GitHub REST API)."""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from google.cloud import storage

from model_onboarding.config import (
    OnboardingSettings,
    get_onboarding_settings,
    resolve_github_token,
    validate_model_slug,
    validate_safe_identifier,
)
from model_onboarding.hygiene_gate import render_hygiene_exception_markdown
from model_onboarding.models import (
    HygieneGateReport,
    ParityVerificationReport,
    PullRequestResult,
)
from model_onboarding.sanitizer import audit_generated_package_tree, ensure_contained_path

_SAFE_BRANCH_RE = re.compile(r"^onboard/[a-z0-9\-]+$")


def render_parity_markdown(parity: ParityVerificationReport) -> str:
    """Render Markdown Parity Verification Report embedded in the package and Git PR."""
    status_badge = "PASS" if parity.passed else "FAIL"
    lines = [
        f"# Numeric Parity Verification Report — `{parity.model_slug}-bq-twin`",
        "",
        f"- **Parity Status**: **`{status_badge}`** (`{parity.parity_rate_pct:.2f}%` match across `{parity.total_compared_cells:,}` cells)",
        f"- **Pytest Suite**: `{parity.pytest_passed}` passed, `{parity.pytest_failed}` failed (`verified_locally={parity.verified_locally}`)",
        f"- **Max Error**: `abs={parity.max_abs_error:.3e}`, `rel={parity.max_rel_error:.3e}`",
        f"- **Sandbox Provenance**: `interaction_id={parity.interaction_id or 'local'}`, `repair_turns={parity.repair_turns_used}`",
        "",
    ]
    if parity.sheet_summaries:
        lines.extend(
            [
                "| Sheet Name | Compared Cells | Matched | Mismatched | Max Abs Error | Max Rel Error |",
                "| :--- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for sh in parity.sheet_summaries:
            lines.append(
                f"| `{sh.sheet_name}` | {sh.compared_cells:,} | {sh.matched_cells:,} | "
                f"{sh.mismatched_cells:,} | `{sh.max_abs_error:.3e}` | `{sh.max_rel_error:.3e}` |"
            )
        lines.append("")

    if parity.documented_irreducible_exceptions:
        lines.append("## Documented Irreducible Baseline Exceptions")
        for item in parity.documented_irreducible_exceptions:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def render_pull_request_body(
    hygiene: HygieneGateReport,
    parity: ParityVerificationReport,
    golden_seed_gcs_uri: str,
) -> str:
    """Render comprehensive GitHub Pull Request body combining Go/No-Go, Hygiene Exceptions, and Parity."""
    slug = hygiene.model_slug
    lines = [
        f"## Automated Energy Spreadsheet Onboarding — `{slug}-bq-twin`",
        "",
        "| Dimension | Value |",
        "| :--- | :--- |",
        f"| **Pre-Flight Verdict** | **`{hygiene.decision.value}`** ({hygiene.readiness_tier}) |",
        f"| **Source Workbook** | `{hygiene.workbook_name}` (`{hygiene.archetype}`) |",
        f"| **Readiness Scores** | `MES={hygiene.mes_score:.1f}%` · `MHS={hygiene.mhs_score:.1f}%` · `MDR={hygiene.mdr_score:.1f}%` · `MRI={hygiene.mri_score:.1f}%` |",
        f"| **Numeric Parity** | **`{parity.parity_rate_pct:.2f}%`** (`{parity.total_matched_cells:,}/{parity.total_compared_cells:,}` cells, `pytest={parity.pytest_passed} passed`, `verified_locally={parity.verified_locally}`) |",
        f"| **Golden Vault Seed** | `{golden_seed_gcs_uri or 'Local dry-run (not uploaded)'}` |",
        "",
        "### 1. Go / No-Go Rationale",
    ]
    for r in hygiene.decision_rationale:
        lines.append(f"- {r}")

    lines.extend(["", "### 2. Workbook Hygiene Exception Summary"])
    if not hygiene.exceptions:
        lines.append("- Zero hygiene or structural exceptions detected.")
    else:
        lines.extend(
            [
                "",
                "| Severity | Sub-Metric | Code | Affected | Sample Coordinates |",
                "| :---: | :---: | :--- | ---: | :--- |",
            ]
        )
        for ex in hygiene.exceptions[:12]:
            samples = ", ".join(f"`{c}`" for c in ex.sample_locations[:4]) or "—"
            lines.append(
                f"| **{ex.severity}** | `{ex.sub_metric}` | `{ex.code}` | {ex.affected_count:,} | {samples} |"
            )

    lines.extend(
        [
            "",
            "### 3. Post-Review Deployment",
            "After reviewing and merging this PR, provision the isolated BigQuery Digital Twin, `ARIMA_PLUS` models, Cloud Run MCP service, and Agent Registry skills via Cowork (`deploy_approved_onboarding_model`) or CLI:",
            "```bash",
            f"onboard deploy {slug}",
            "```",
        ]
    )
    return "\n".join(lines)


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60.0,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def archive_seed_to_vault(
    xlsx_path: Path,
    model_slug: str,
    settings: OnboardingSettings,
    gcs_client: storage.Client | None = None,
) -> str:
    """Upload baseline `.xlsx`/`.xlsm` to GCS Golden Seed Vault (`golden-seed/<slug>/<filename>`)."""
    safe_slug = validate_model_slug(model_slug)
    safe_filename = Path(xlsx_path.name).name
    client = gcs_client or storage.Client(project=settings.gcp_project_id)
    bucket = client.bucket(settings.vault_bucket or settings.staging_bucket)
    blob_path = f"golden-seed/{safe_slug}/{safe_filename}"
    bucket.blob(blob_path).upload_from_filename(str(xlsx_path))
    return f"gs://{bucket.name}/{blob_path}"


def _github_api_request(
    method: str,
    github_repo: str,
    subpath: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{github_repo}/{subpath.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"GitHub API {method} {subpath} failed (HTTP {exc.code}): {detail}") from exc


def _write_reports_into_package(
    target_pkg: Path,
    hygiene: HygieneGateReport,
    parity: ParityVerificationReport,
) -> None:
    reports_dir = ensure_contained_path(target_pkg, target_pkg / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "hygiene_exception_report.json").write_text(
        json.dumps(hygiene.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    (reports_dir / "hygiene_exception_report.md").write_text(
        render_hygiene_exception_markdown(hygiene),
        encoding="utf-8",
    )
    (reports_dir / "parity_report.json").write_text(
        json.dumps(parity.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    (reports_dir / "parity_verification_report.md").write_text(
        render_parity_markdown(parity),
        encoding="utf-8",
    )


def publish_via_github_git_data_api(
    github_repo: str,
    base_branch: str,
    branch_name: str,
    commit_msg: str,
    pr_title: str,
    pr_body: str,
    staged_pkg_dir: Path,
    model_slug: str,
    token: str,
) -> tuple[str, str, int | None]:
    """Commit `<slug>-bq-twin/` and open a PR purely via GitHub Git Data REST API (zero local `.git`)."""
    clean_files = audit_generated_package_tree(staged_pkg_dir)
    ref_info = _github_api_request("GET", github_repo, f"git/ref/heads/{base_branch}", token)
    base_commit_sha = str(ref_info["object"]["sha"])
    commit_info = _github_api_request("GET", github_repo, f"git/commits/{base_commit_sha}", token)
    base_tree_sha = str(commit_info["tree"]["sha"])

    pkg_root = staged_pkg_dir.resolve()
    tree_entries: list[dict[str, str]] = []
    for file_path in clean_files:
        rel_posix = file_path.relative_to(pkg_root).as_posix()
        b64_content = base64.b64encode(file_path.read_bytes()).decode("ascii")
        blob_resp = _github_api_request(
            "POST",
            github_repo,
            "git/blobs",
            token,
            {"content": b64_content, "encoding": "base64"},
        )
        tree_entries.append(
            {
                "path": f"{model_slug}-bq-twin/{rel_posix}",
                "mode": "100644",
                "type": "blob",
                "sha": str(blob_resp["sha"]),
            }
        )

    tree_resp = _github_api_request(
        "POST",
        github_repo,
        "git/trees",
        token,
        {"base_tree": base_tree_sha, "tree": tree_entries},
    )
    new_commit = _github_api_request(
        "POST",
        github_repo,
        "git/commits",
        token,
        {
            "message": commit_msg,
            "tree": str(tree_resp["sha"]),
            "parents": [base_commit_sha],
        },
    )
    commit_sha = str(new_commit["sha"])

    try:
        _github_api_request(
            "POST",
            github_repo,
            "git/refs",
            token,
            {"ref": f"refs/heads/{branch_name}", "sha": commit_sha},
        )
    except RuntimeError:
        _github_api_request(
            "PATCH",
            github_repo,
            f"git/refs/heads/{branch_name}",
            token,
            {"sha": commit_sha, "force": True},
        )

    pr_resp = _github_api_request(
        "POST",
        github_repo,
        "pulls",
        token,
        {
            "title": pr_title,
            "head": branch_name,
            "base": base_branch,
            "body": pr_body,
        },
    )
    pr_url = str(pr_resp.get("html_url") or "")
    pr_num = int(pr_resp.get("number") or 0) or None
    return commit_sha, pr_url, pr_num


def publish_onboarding_branch_and_pr(
    repo_root: Path,
    job_id: str,
    sanitized_pkg_dir: Path,
    xlsx_path: Path,
    hygiene: HygieneGateReport,
    parity: ParityVerificationReport,
    local_only: bool = False,
    prefer_github_api: bool = False,
    settings: OnboardingSettings | None = None,
    gcs_client: storage.Client | None = None,
) -> PullRequestResult:
    """Commit sanitized `<slug>-bq-twin/` + reports via local `git worktree` or repo-free GitHub REST API."""
    cfg = settings or get_onboarding_settings()
    resolved_repo = repo_root.expanduser().resolve()
    safe_slug = validate_model_slug(hygiene.model_slug)
    short_job = re.sub(r"[^a-z0-9]+", "", validate_safe_identifier(job_id, "job_id").lower())[:8] or "run"
    branch_name = f"onboard/{safe_slug}-{short_job}"
    if not _SAFE_BRANCH_RE.match(branch_name):
        raise ValueError(f"Invalid onboarding branch name: {branch_name!r}")

    audit_generated_package_tree(sanitized_pkg_dir)

    golden_uri = ""
    if not local_only:
        golden_uri = archive_seed_to_vault(xlsx_path, safe_slug, cfg, gcs_client=gcs_client)

    commit_msg = (
        f"feat({safe_slug}-bq-twin): onboard BigQuery Digital Twin, solver, and MCP server "
        f"[{hygiene.decision.value} | parity {parity.parity_rate_pct:.1f}%]"
    )
    pr_title = f"feat({safe_slug}-bq-twin): onboard {hygiene.workbook_name} Digital Twin [{hygiene.decision.value}]"
    pr_body = render_pull_request_body(hygiene, parity, golden_uri)

    has_local_git = (resolved_repo / ".git").exists()

    # Cloud Run / Repo-Free Mode: commit directly via GitHub Git Data REST API
    if not local_only and (prefer_github_api or not has_local_git):
        token = resolve_github_token()
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN / ONBOARD_GITHUB_TOKEN is required for repo-free GitHub PR creation."
            )
        with tempfile.TemporaryDirectory(prefix="onboard_gh_api_") as tmp_stage:
            staged_pkg = ensure_contained_path(Path(tmp_stage), Path(tmp_stage) / f"{safe_slug}-bq-twin")
            shutil.copytree(sanitized_pkg_dir, staged_pkg)
            _write_reports_into_package(staged_pkg, hygiene, parity)
            commit_sha, pr_url, pr_number = publish_via_github_git_data_api(
                github_repo=cfg.github_repo,
                base_branch=cfg.base_git_branch,
                branch_name=branch_name,
                commit_msg=commit_msg,
                pr_title=pr_title,
                pr_body=pr_body,
                staged_pkg_dir=staged_pkg,
                model_slug=safe_slug,
                token=token,
            )
        return PullRequestResult(
            model_slug=safe_slug,
            branch_name=branch_name,
            commit_sha=commit_sha,
            package_dir=f"{safe_slug}-bq-twin",
            golden_seed_gcs_uri=golden_uri,
            pr_url=pr_url,
            pr_number=pr_number,
            local_only=False,
        )

    # Local Git Worktree Mode (CLI & offline tests)
    with tempfile.TemporaryDirectory(prefix="onboard_wt_") as tmp_wt:
        wt_path = Path(tmp_wt) / "tree"
        base_ref = cfg.base_git_branch
        _run_git(["worktree", "add", "-B", branch_name, str(wt_path), base_ref], cwd=resolved_repo)
        try:
            target_pkg = ensure_contained_path(wt_path, wt_path / f"{safe_slug}-bq-twin")
            if target_pkg.exists():
                shutil.rmtree(target_pkg)
            shutil.copytree(sanitized_pkg_dir, target_pkg)
            _write_reports_into_package(target_pkg, hygiene, parity)
            audit_generated_package_tree(target_pkg)

            _run_git(["add", f"{safe_slug}-bq-twin"], cwd=wt_path)
            _run_git(["commit", "-m", commit_msg], cwd=wt_path)
            commit_sha = _run_git(["rev-parse", "HEAD"], cwd=wt_path)
        finally:
            _run_git(["worktree", "remove", "--force", str(wt_path)], cwd=resolved_repo)

    pr_url = ""
    pr_number: int | None = None
    if not local_only:
        _run_git(["push", "-u", "origin", branch_name], cwd=resolved_repo)
        token = resolve_github_token()
        if not token:
            raise RuntimeError(
                "Branch pushed, but GITHUB_TOKEN / ONBOARD_GITHUB_TOKEN is not set to open the Pull Request."
            )
        pr_resp = _github_api_request(
            "POST",
            cfg.github_repo,
            "pulls",
            token,
            {
                "title": pr_title,
                "head": branch_name,
                "base": cfg.base_git_branch,
                "body": pr_body,
            },
        )
        pr_url = str(pr_resp.get("html_url") or "")
        pr_number = int(pr_resp.get("number") or 0) or None

    return PullRequestResult(
        model_slug=safe_slug,
        branch_name=branch_name,
        commit_sha=commit_sha,
        package_dir=f"{safe_slug}-bq-twin",
        golden_seed_gcs_uri=golden_uri,
        pr_url=pr_url,
        pr_number=pr_number,
        local_only=local_only,
    )
