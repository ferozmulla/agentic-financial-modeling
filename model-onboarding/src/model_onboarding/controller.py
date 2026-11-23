"""Stateful Onboarding Controller coordinating Stages 1, 2, and 3 across CLI, Cowork, and Cloud Run MCP."""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from google.cloud import storage

from model_onboarding.config import (
    OnboardingSettings,
    derive_default_slug,
    get_onboarding_settings,
    validate_model_slug,
    validate_safe_identifier,
)
from model_onboarding.deployer import deploy_onboarded_model
from model_onboarding.hygiene_gate import evaluate_workbook_hygiene, validate_workbook_file
from model_onboarding.models import (
    DeploymentSummary,
    GoNoGoDecision,
    HygieneGateReport,
    OnboardingJobState,
    OnboardingJobStatus,
    UploadSessionInfo,
)
from model_onboarding.pr_publisher import publish_onboarding_branch_and_pr
from model_onboarding.sandbox_worker import CodegenSandboxWorker, ManagedAgentsSandboxWorker
from model_onboarding.sanitizer import ensure_contained_path

_SAFE_UPLOAD_FILENAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
_ALLOWED_UPLOAD_SUFFIXES = {".xlsx", ".xlsm"}


def sanitize_upload_workbook_name(raw_filename: str) -> str:
    """Sanitize uploaded `.xlsx`/`.xlsm` filename against traversal and header injection."""
    base = Path(raw_filename).name.strip()
    suffix = Path(base).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        raise ValueError(f"Unsupported workbook extension {suffix!r}; only .xlsx and .xlsm are allowed.")
    stem = re.sub(r"[^A-Za-z0-9._\-]+", "_", Path(base).stem).strip("._-") or "workbook"
    safe = f"{stem[:80]}{suffix}"
    if not _SAFE_UPLOAD_FILENAME_RE.match(safe) or ".." in safe:
        raise ValueError(f"Invalid workbook filename: {raw_filename!r}")
    return safe


def content_type_for_workbook(filename: str) -> str:
    if filename.lower().endswith(".xlsm"):
        return "application/vnd.ms-excel.sheet.macroEnabled.12"
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def resolve_workbook_input(
    source_path_or_gcs_uri: str,
    scratch_dir: Path,
    settings: OnboardingSettings,
    gcs_client: storage.Client | None = None,
) -> Path:
    """Resolve either a local `.xlsx`/`.xlsm` path or a `gs://bucket/object` URI into a validated local file."""
    raw = source_path_or_gcs_uri.strip()
    if raw.startswith("gs://"):
        without_scheme = raw[5:]
        if "/" not in without_scheme:
            raise ValueError(f"Invalid GCS URI: {raw!r}")
        bucket_name, blob_name = without_scheme.split("/", 1)
        validate_safe_identifier(bucket_name, "gcs_bucket")
        safe_name = sanitize_upload_workbook_name(Path(blob_name).name)
        dest = ensure_contained_path(scratch_dir, scratch_dir / safe_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        client = gcs_client or storage.Client(project=settings.gcp_project_id)
        client.bucket(bucket_name).blob(blob_name).download_to_filename(str(dest))
        return validate_workbook_file(dest, max_size_mb=settings.max_workbook_size_mb)

    return validate_workbook_file(Path(raw), max_size_mb=settings.max_workbook_size_mb)


class OnboardingController:
    """End-to-end orchestrator shared by the Admin CLI (`onboard`), Cowork, and Cloud Run MCP."""

    def __init__(
        self,
        repo_root: Path | None = None,
        settings: OnboardingSettings | None = None,
        sandbox_worker: CodegenSandboxWorker | None = None,
        gcs_client: storage.Client | None = None,
    ) -> None:
        self.settings = settings or get_onboarding_settings()
        self.repo_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
        self._gcs_client = gcs_client
        self.sandbox_worker = sandbox_worker or ManagedAgentsSandboxWorker(
            settings=self.settings,
            gcs_client=gcs_client,
        )

    def _gcs_enabled(self) -> bool:
        return self._gcs_client is not None

    def _job_status_path(self, job_id: str) -> Path:
        safe_job = validate_safe_identifier(job_id, "job_id")
        jobs_root = self.settings.local_jobs_dir.expanduser().resolve()
        jobs_root.mkdir(parents=True, exist_ok=True)
        return ensure_contained_path(jobs_root, jobs_root / f"{safe_job}.json")

    def save_job_status(self, status: OnboardingJobStatus) -> OnboardingJobStatus:
        """Persist job status locally and mirror to GCS when configured for stateless Cloud Run instances."""
        updated = status.model_copy(update={"updated_at_utc": datetime.now(UTC).isoformat()})
        payload_txt = json.dumps(updated.model_dump(mode="json"), indent=2)
        path = self._job_status_path(updated.job_id)
        path.write_text(payload_txt, encoding="utf-8")

        if self._gcs_enabled():
            try:
                assert self._gcs_client is not None
                blob = self._gcs_client.bucket(self.settings.staging_bucket).blob(
                    f"jobs/{updated.job_id}/status.json"
                )
                blob.upload_from_string(payload_txt, content_type="application/json")
            except (OSError, RuntimeError, ValueError):
                pass
        return updated

    def get_job_status(self, job_id: str) -> OnboardingJobStatus:
        safe_job = validate_safe_identifier(job_id, "job_id")
        path = self._job_status_path(safe_job)
        if path.exists():
            return OnboardingJobStatus.model_validate(json.loads(path.read_text(encoding="utf-8")))

        if self._gcs_enabled():
            assert self._gcs_client is not None
            blob = self._gcs_client.bucket(self.settings.staging_bucket).blob(f"jobs/{safe_job}/status.json")
            if blob.exists():
                raw = blob.download_as_text(encoding="utf-8")
                path.write_text(raw, encoding="utf-8")
                return OnboardingJobStatus.model_validate(json.loads(raw))

        raise FileNotFoundError(f"Onboarding job not found: {job_id!r}")

    def create_upload_session(self, filename: str, base_url: str = "") -> UploadSessionInfo:
        """Mint a short-lived GCS V4 Signed PUT URL + `/v1/uploads` fallback for Cowork `+` attachments."""
        safe_name = sanitize_upload_workbook_name(filename)
        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        ctype = content_type_for_workbook(safe_name)
        blob_path = f"uploads/{upload_id}/{safe_name}"
        gcs_uri = f"gs://{self.settings.staging_bucket}/{blob_path}"

        effective_base = (base_url or self.settings.public_service_url).rstrip("/")
        direct_post = f"{effective_base}/v1/uploads/{upload_id}/{safe_name}" if effective_base else ""

        signed_url = ""
        try:
            client = self._gcs_client or storage.Client(project=self.settings.gcp_project_id)
            blob = client.bucket(self.settings.staging_bucket).blob(blob_path)
            sign_kwargs: dict[str, object] = {
                "version": "v4",
                "expiration": timedelta(seconds=900),
                "method": "PUT",
                "content_type": ctype,
            }
            if self.settings.service_account_email:
                import google.auth
                from google.auth.transport.requests import Request

                creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
                creds.refresh(Request())
                sign_kwargs["service_account_email"] = self.settings.service_account_email
                sign_kwargs["access_token"] = creds.token
            signed_url = str(blob.generate_signed_url(**sign_kwargs))
        except Exception:  # noqa: BLE001 — fallback cleanly to direct_post_url when ADC lacks local signing key
            signed_url = ""

        return UploadSessionInfo(
            upload_id=upload_id,
            filename=safe_name,
            workbook_gcs_uri=gcs_uri,
            signed_put_url=signed_url,
            direct_post_url=direct_post,
            content_type=ctype,
            expires_in_seconds=900,
        )

    def store_uploaded_workbook_bytes(
        self,
        upload_id: str,
        filename: str,
        raw_bytes: bytes,
        upload_to_gcs: bool = True,
    ) -> str:
        """Validate OpenXML workbook bytes from `POST /v1/uploads` and stage to GCS (or local staging)."""
        safe_upl = validate_safe_identifier(upload_id, "upload_id")
        safe_name = sanitize_upload_workbook_name(filename)
        max_bytes = int(self.settings.max_workbook_size_mb * 1024 * 1024)
        if len(raw_bytes) > max_bytes:
            raise ValueError(f"Uploaded workbook exceeds {self.settings.max_workbook_size_mb:.1f} MB limit.")

        uploads_root = (self.settings.local_jobs_dir.expanduser().resolve() / "uploads" / safe_upl).resolve()
        uploads_root.mkdir(parents=True, exist_ok=True)
        local_dest = ensure_contained_path(uploads_root, uploads_root / safe_name)
        local_dest.write_bytes(raw_bytes)

        # Validate ZIP magic header + [Content_Types].xml + xl/workbook.xml before accepting
        validate_workbook_file(local_dest, max_size_mb=self.settings.max_workbook_size_mb)

        if upload_to_gcs:
            client = self._gcs_client or storage.Client(project=self.settings.gcp_project_id)
            blob_path = f"uploads/{safe_upl}/{safe_name}"
            client.bucket(self.settings.staging_bucket).blob(blob_path).upload_from_filename(
                str(local_dest),
                content_type=content_type_for_workbook(safe_name),
            )
            return f"gs://{self.settings.staging_bucket}/{blob_path}"

        return str(local_dest)

    def assess_only(
        self,
        source_path_or_gcs_uri: str,
        model_slug: str | None = None,
        reference_roots: list[Path] | None = None,
    ) -> HygieneGateReport:
        """Execute Stage 1 deterministic Hygiene & Go/No-Go assessment without running Stage 2."""
        with tempfile.TemporaryDirectory(prefix="onboard_assess_") as tmp:
            wb_path = resolve_workbook_input(
                source_path_or_gcs_uri,
                Path(tmp),
                self.settings,
                gcs_client=self._gcs_client,
            )
            return evaluate_workbook_hygiene(
                xlsx_path=wb_path,
                model_slug=model_slug,
                reference_roots=reference_roots or [],
                settings=self.settings,
            )

    def create_pending_job(self, source_path_or_gcs_uri: str, model_slug: str | None = None) -> OnboardingJobStatus:
        """Create and persist a new `OnboardingJobStatus` envelope."""
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        inferred_name = Path(source_path_or_gcs_uri.rstrip("/")).name
        slug = validate_model_slug(model_slug or derive_default_slug(inferred_name))
        status = OnboardingJobStatus(
            job_id=job_id,
            model_slug=slug,
            source_workbook=source_path_or_gcs_uri,
            state=OnboardingJobState.PENDING,
        )
        return self.save_job_status(status)

    def execute_job(
        self,
        job_id: str,
        force_override: bool = False,
        local_branch_only: bool = False,
        reference_roots: list[Path] | None = None,
    ) -> OnboardingJobStatus:
        """Run Stages 1 -> 2 -> 3a synchronously for `job_id`, updating persisted state at each step."""
        status = self.get_job_status(job_id)
        try:
            with tempfile.TemporaryDirectory(prefix=f"onboard_{status.job_id}_") as tmp:
                tmp_root = Path(tmp)
                status = self.save_job_status(
                    status.model_copy(update={"state": OnboardingJobState.ASSESSING_HYGIENE})
                )
                wb_path = resolve_workbook_input(
                    status.source_workbook,
                    tmp_root / "source",
                    self.settings,
                    gcs_client=self._gcs_client,
                )
                hygiene = evaluate_workbook_hygiene(
                    xlsx_path=wb_path,
                    model_slug=status.model_slug,
                    reference_roots=reference_roots or [],
                    settings=self.settings,
                )
                status = self.save_job_status(status.model_copy(update={"hygiene_report": hygiene}))

                if hygiene.decision == GoNoGoDecision.NO_GO and not force_override:
                    return self.save_job_status(
                        status.model_copy(
                            update={
                                "state": OnboardingJobState.BLOCKED_NO_GO,
                                "error_message": "Blocked by Stage 1 NO_GO hygiene policy (pass --force to override).",
                            }
                        )
                    )

                status = self.save_job_status(
                    status.model_copy(update={"state": OnboardingJobState.RUNNING_SANDBOX_CODEGEN})
                )
                pkg_dir, parity = self.sandbox_worker.generate_and_verify_twin(
                    job_id=status.job_id,
                    xlsx_path=wb_path,
                    hygiene_report=hygiene,
                    work_dir=tmp_root / "sandbox",
                )

                status = self.save_job_status(
                    status.model_copy(
                        update={
                            "state": OnboardingJobState.PUBLISHING_PR,
                            "parity_report": parity,
                        }
                    )
                )
                pr_result = publish_onboarding_branch_and_pr(
                    repo_root=self.repo_root,
                    job_id=status.job_id,
                    sanitized_pkg_dir=pkg_dir,
                    xlsx_path=wb_path,
                    hygiene=hygiene,
                    parity=parity,
                    local_only=local_branch_only,
                    settings=self.settings,
                    gcs_client=self._gcs_client,
                )
                return self.save_job_status(
                    status.model_copy(
                        update={
                            "state": OnboardingJobState.AWAITING_PR_APPROVAL,
                            "pr_result": pr_result,
                        }
                    )
                )
        except (OSError, RuntimeError, ValueError, KeyError, LookupError) as exc:
            return self.save_job_status(
                status.model_copy(
                    update={
                        "state": OnboardingJobState.FAILED,
                        "error_message": str(exc)[:600],
                    }
                )
            )

    def deploy_approved(
        self,
        model_slug: str,
        skip_bqml: bool = False,
        pr_number: int | None = None,
        require_merged_pr: bool = False,
    ) -> DeploymentSummary:
        """Execute Stage 3b deterministic deployment for an approved `<model_slug>-bq-twin/`."""
        return deploy_onboarded_model(
            repo_root=self.repo_root,
            model_slug=model_slug,
            skip_bqml=skip_bqml,
            pr_number=pr_number,
            require_merged_pr=require_merged_pr,
            settings=self.settings,
        )
