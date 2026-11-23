"""Stage 2: Google Cloud Managed Agents API (`v1beta1`) Sandbox Worker & Parity Repair Loop."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from google.cloud import storage

from model_onboarding.config import (
    OnboardingSettings,
    get_onboarding_settings,
    validate_model_slug,
    validate_safe_identifier,
)
from model_onboarding.models import HygieneGateReport, ParityVerificationReport
from model_onboarding.sanitizer import (
    audit_generated_package_tree,
    ensure_contained_path,
    extract_tar_safely,
    run_local_parity_pytest,
)
from model_onboarding.vba_extractor import stage_extracted_vba_modules

logger = logging.getLogger(__name__)

MANAGED_AGENTS_API_REVISION = "2026-05-20"


class CodegenSandboxWorker(Protocol):
    """Protocol abstracting Stage 2 autonomous Digital Twin & Solver generation."""

    def generate_and_verify_twin(
        self,
        job_id: str,
        xlsx_path: Path,
        hygiene_report: HygieneGateReport,
        work_dir: Path,
    ) -> tuple[Path, ParityVerificationReport]:
        """Generate `<model_slug>-bq-twin/` and verify parity against `xlsx_path`."""


def _sandbox_bundle_root() -> Path:
    return Path(__file__).resolve().parents[2] / "sandbox_bundle" / "skills" / "energy-twin-builder"


def build_sandbox_onboarding_prompt(hygiene_report: HygieneGateReport) -> str:
    """Build deterministic initial prompt instructing `antigravity-preview-05-2026` inside the sandbox."""
    slug = hygiene_report.model_slug
    wb_name = hygiene_report.workbook_name
    return (
        f"Read and follow `/.agent/skills/energy-twin-builder/SKILL.md` to onboard `{wb_name}` "
        f"into `/.agent/job/output/{slug}-bq-twin/`.\n\n"
        f"Key Stage 1 Hygiene Parameters:\n"
        f"- model_slug: `{slug}`\n"
        f"- archetype: `{hygiene_report.archetype}`\n"
        f"- mes_score: {hygiene_report.mes_score:.1f}% | mdr_score: {hygiene_report.mdr_score:.1f}%\n"
        f"- is_iterative_calc: {hygiene_report.is_iterative_calc} (iterate_count={hygiene_report.iterate_count})\n"
        f"- candidate_assumption_sheets: {hygiene_report.candidate_assumption_sheets}\n"
        f"- candidate_timeseries_sheets (BQML ARIMA_PLUS): {hygiene_report.candidate_timeseries_sheets}\n"
        f"- vba_modules (staged in `/.agent/job/input/vba_modules/`): {hygiene_report.vba_modules}\n\n"
        f"Deliverables required inside `/.agent/job/output/`:\n"
        f"1. Complete `{slug}-bq-twin/` package (zero `.xlsx`/`.xlsm` binaries inside `{slug}-bq-twin/`).\n"
        f"2. Passing `pytest` numeric parity suite in `{slug}-bq-twin/tests/test_parity.py`.\n"
        f"3. `parity_report.json` and `parity_verification_report.md`."
    )


def parse_interactions_sse_stream(lines: list[str]) -> tuple[str, str, str]:
    """Parse SSE event lines from `POST .../interactions` into `(interaction_id, environment_id, status)`."""
    interaction_id = ""
    environment_id = ""
    status = "unknown"

    for raw_line in lines:
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload_txt = line[5:].strip()
        if not payload_txt or not payload_txt.startswith("{"):
            continue
        try:
            event_obj = json.loads(payload_txt)
        except json.JSONDecodeError:
            continue

        inter = event_obj.get("interaction")
        if isinstance(inter, dict):
            interaction_id = str(inter.get("id") or interaction_id)
            environment_id = str(inter.get("environment_id") or environment_id)
            status = str(inter.get("status") or status)
        elif "id" in event_obj and "status" in event_obj:
            interaction_id = str(event_obj.get("id") or interaction_id)
            environment_id = str(event_obj.get("environment_id") or environment_id)
            status = str(event_obj.get("status") or status)

    return interaction_id, environment_id, status


class ManagedAgentsSandboxWorker:
    """Stage 2 worker invoking Google Cloud Managed Agents API (`antigravity-preview-05-2026`)."""

    def __init__(
        self,
        settings: OnboardingSettings | None = None,
        gcs_client: storage.Client | None = None,
    ) -> None:
        self.settings = settings or get_onboarding_settings()
        self._gcs = gcs_client

    @property
    def gcs(self) -> storage.Client:
        if self._gcs is None:
            self._gcs = storage.Client(project=self.settings.gcp_project_id)
        return self._gcs

    def _get_access_token(self) -> str:
        import google.auth
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        if not creds.token:
            raise RuntimeError("Failed to obtain Google Cloud ADC token for Managed Agents API.")
        return str(creds.token)

    def _upload_directory_to_gcs(self, bucket_name: str, local_dir: Path, gcs_prefix: str) -> None:
        bucket = self.gcs.bucket(bucket_name)
        root = local_dir.resolve()
        for file_path in sorted(root.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                rel = file_path.relative_to(root).as_posix()
                blob = bucket.blob(f"{gcs_prefix.rstrip('/')}/{rel}")
                blob.upload_from_filename(str(file_path))

    def _stage_job_inputs(
        self,
        job_id: str,
        xlsx_path: Path,
        hygiene_report: HygieneGateReport,
        work_dir: Path,
    ) -> str:
        safe_job = validate_safe_identifier(job_id, "job_id")
        bucket_name = self.settings.staging_bucket

        # 1. Sync read-only energy-twin-builder skill bundle
        skill_root = _sandbox_bundle_root()
        if skill_root.exists():
            self._upload_directory_to_gcs(
                bucket_name,
                skill_root,
                "skills/energy-twin-builder",
            )

        # 2. Stage workbook, hygiene JSON, and extracted VBA modules into job-scoped prefix
        local_input = work_dir / "staged_input"
        local_input.mkdir(parents=True, exist_ok=True)
        (local_input / "hygiene_exception_report.json").write_text(
            json.dumps(hygiene_report.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        stage_extracted_vba_modules(xlsx_path, local_input / "vba_modules")

        job_prefix = f"jobs/{safe_job}"
        self._upload_directory_to_gcs(bucket_name, local_input, f"{job_prefix}/input")
        bucket = self.gcs.bucket(bucket_name)
        bucket.blob(f"{job_prefix}/input/{xlsx_path.name}").upload_from_filename(str(xlsx_path))
        return f"gs://{bucket_name}/{job_prefix}"

    def _invoke_interaction(
        self,
        prompt_text: str,
        job_gcs_uri: str,
        previous_interaction_id: str = "",
        environment_id: str = "",
    ) -> tuple[str, str, str]:
        project = validate_safe_identifier(self.settings.gcp_project_id, "gcp_project_id")
        location = validate_safe_identifier(
            self.settings.managed_agents_location, "managed_agents_location"
        )
        url = f"https://aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/interactions"

        env_payload: Any
        if environment_id:
            env_payload = environment_id
        else:
            env_payload = {
                "type": "remote",
                "sources": [
                    {
                        "type": "gcs",
                        "source": f"gs://{self.settings.staging_bucket}/skills",
                        "target": "/.agent/skills",
                    },
                    {
                        "type": "gcs",
                        "source": job_gcs_uri,
                        "target": "/.agent/job",
                    },
                ],
                "network": {
                    "allowlist": [
                        {"domain": "pypi.org"},
                        {"domain": "files.pythonhosted.org"},
                    ]
                },
            }

        body: dict[str, Any] = {
            "stream": True,
            "background": True,
            "store": True,
            "agent": self.settings.base_agent,
            "environment": env_payload,
            "input": [
                {
                    "type": "user_input",
                    "content": [{"type": "text", "text": prompt_text}],
                }
            ],
        }
        if previous_interaction_id:
            body["previous_interaction_id"] = previous_interaction_id

        token = self._get_access_token()
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Api-Revision": MANAGED_AGENTS_API_REVISION,
            },
            method="POST",
        )
        if not url.startswith("https://"):
            raise ValueError("Managed Agents API endpoint must use HTTPS.")

        try:
            with urllib.request.urlopen(req, timeout=self.settings.interaction_timeout_sec) as resp:
                raw_lines = resp.read().decode("utf-8", errors="replace").splitlines()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Managed Agents Interactions API HTTP {exc.code}: {detail}") from exc

        return parse_interactions_sse_stream(raw_lines)

    def _download_job_outputs(
        self,
        job_id: str,
        model_slug: str,
        download_dir: Path,
    ) -> tuple[Path, ParityVerificationReport | None]:
        safe_job = validate_safe_identifier(job_id, "job_id")
        safe_slug = validate_model_slug(model_slug)
        out_prefix = f"jobs/{safe_job}/output/"
        bucket = self.gcs.bucket(self.settings.staging_bucket)

        resolved_dl = download_dir.expanduser().resolve()
        resolved_dl.mkdir(parents=True, exist_ok=True)

        blobs = list(bucket.list_blobs(prefix=out_prefix))
        for blob in blobs:
            rel = blob.name[len(out_prefix) :].lstrip("/")
            if not rel or blob.name.endswith("/"):
                continue
            parts = Path(rel).parts
            if ".." in parts:
                raise ValueError(f"Unsafe GCS output blob path: {blob.name!r}")
            dest_file = ensure_contained_path(resolved_dl, resolved_dl / rel)
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(dest_file))

        pkg_dir = resolved_dl / f"{safe_slug}-bq-twin"
        tar_candidate = resolved_dl / "package.tar.gz"
        if not pkg_dir.exists() and tar_candidate.exists():
            extract_tar_safely(tar_candidate, resolved_dl)

        parity_json = resolved_dl / "parity_report.json"
        parity_report: ParityVerificationReport | None = None
        if parity_json.exists():
            raw_parity = json.loads(parity_json.read_text(encoding="utf-8"))
            raw_parity.setdefault("model_slug", safe_slug)
            parity_report = ParityVerificationReport.model_validate(raw_parity)

        return pkg_dir, parity_report

    def generate_and_verify_twin(
        self,
        job_id: str,
        xlsx_path: Path,
        hygiene_report: HygieneGateReport,
        work_dir: Path,
    ) -> tuple[Path, ParityVerificationReport]:
        """Stage inputs to GCS, invoke Managed Agent with repair turns, sanitize output, and re-verify parity locally."""
        resolved_work = work_dir.expanduser().resolve()
        resolved_work.mkdir(parents=True, exist_ok=True)

        job_gcs_uri = self._stage_job_inputs(job_id, xlsx_path, hygiene_report, resolved_work)
        prompt = build_sandbox_onboarding_prompt(hygiene_report)

        inter_id, env_id, _status = self._invoke_interaction(prompt_text=prompt, job_gcs_uri=job_gcs_uri)
        repair_turns = 0

        dl_dir = resolved_work / "downloaded_output"
        pkg_dir, parity_report = self._download_job_outputs(
            job_id=job_id,
            model_slug=hygiene_report.model_slug,
            download_dir=dl_dir,
        )

        while (
            not pkg_dir.exists() or parity_report is None or not parity_report.passed
        ) and repair_turns < self.settings.max_repair_turns:
            repair_turns += 1
            repair_prompt = (
                f"Output verification check #{repair_turns}: ensure `/.agent/job/output/{hygiene_report.model_slug}-bq-twin/` "
                f"exists with all required modules, re-run `pytest` against `/.agent/job/input/{hygiene_report.workbook_name}`, "
                f"fix any remaining numeric parity mismatches, and write `/.agent/job/output/parity_report.json` with `passed=true`."
            )
            inter_id, env_id, _status = self._invoke_interaction(
                prompt_text=repair_prompt,
                job_gcs_uri=job_gcs_uri,
                previous_interaction_id=inter_id,
                environment_id=env_id,
            )
            pkg_dir, parity_report = self._download_job_outputs(
                job_id=job_id,
                model_slug=hygiene_report.model_slug,
                download_dir=dl_dir,
            )

        if not pkg_dir.exists() or parity_report is None:
            raise RuntimeError(
                f"Managed Agent job {job_id} did not produce {hygiene_report.model_slug}-bq-twin and parity_report.json."
            )

        # Security audit + independent local pytest parity verification
        audit_generated_package_tree(pkg_dir)
        verified_parity = run_local_parity_pytest(
            pkg_dir=pkg_dir,
            seed_workbook_path=xlsx_path,
            parity_report=parity_report.model_copy(
                update={
                    "interaction_id": inter_id,
                    "environment_id": env_id,
                    "repair_turns_used": repair_turns,
                }
            ),
        )
        return pkg_dir, verified_parity
