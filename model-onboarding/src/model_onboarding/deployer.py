"""Stage 3b: Deterministic Post-PR-Approval Deployer (Local CLI + Repo-Free Cloud Build / Cloud Run APIs)."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import yaml
from google.cloud import storage

from model_onboarding.config import (
    OnboardingSettings,
    get_onboarding_settings,
    resolve_github_token,
    validate_model_slug,
    validate_safe_identifier,
)
from model_onboarding.models import DeploymentSummary
from model_onboarding.sanitizer import (
    audit_generated_package_tree,
    ensure_contained_path,
    extract_tar_safely,
)

AGENT_REGISTRY_MCP_URL = "https://agentregistry.googleapis.com/mcp"


def _get_gcp_token() -> str:
    import google.auth
    from google.auth.transport.requests import Request

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    if not creds.token:
        raise RuntimeError("Unable to acquire Google Cloud ADC access token.")
    return str(creds.token)


def _gcp_json_request(
    method: str,
    url: str,
    token: str,
    project_id: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 45.0,
) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ValueError(f"GCP REST URL must use HTTPS: {url!r}")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GCP API {method} {url} HTTP {exc.code}: {detail}") from exc


def verify_pr_merged(github_repo: str, pr_number: int) -> bool:
    """Verify via GitHub REST API that `pr_number` has been merged before deploying."""
    token = resolve_github_token()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{github_repo}/pulls/{int(pr_number)}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return bool(data.get("merged"))


def fetch_package_from_github_tarball(
    github_repo: str,
    git_ref: str,
    model_slug: str,
    scratch_dir: Path,
) -> Path:
    """Download merged `<slug>-bq-twin/` from GitHub `tarball/{git_ref}` when running repo-free on Cloud Run."""
    safe_slug = validate_model_slug(model_slug)
    safe_ref = validate_safe_identifier(git_ref, "git_ref")
    token = resolve_github_token()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{github_repo}/tarball/{safe_ref}"
    tar_path = ensure_contained_path(scratch_dir, scratch_dir / "repo.tar.gz")
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        tar_path.write_bytes(resp.read())

    extracted_root = ensure_contained_path(scratch_dir, scratch_dir / "extracted")
    # Extract only the target `<slug>-bq-twin/` subtree safely
    extracted_root.mkdir(parents=True, exist_ok=True)
    sub_tar_buf = io.BytesIO()
    target_dir_name = f"{safe_slug}-bq-twin"
    found_any = False

    with tarfile.open(tar_path, mode="r:*") as src_tf, tarfile.open(
        fileobj=sub_tar_buf, mode="w:gz"
    ) as dst_tf:
        for member in src_tf.getmembers():
            parts = Path(member.name).parts
            if len(parts) >= 2 and parts[1] == target_dir_name and member.isfile():
                rel_sub = Path(*parts[1:]).as_posix()
                file_obj = src_tf.extractfile(member)
                if file_obj is None:
                    continue
                payload = file_obj.read()
                info = tarfile.TarInfo(name=rel_sub)
                info.size = len(payload)
                dst_tf.addfile(info, io.BytesIO(payload))
                found_any = True

    if not found_any:
        raise FileNotFoundError(
            f"Directory '{target_dir_name}/' was not found on '{github_repo}@{safe_ref}'."
        )

    filtered_tar = ensure_contained_path(scratch_dir, scratch_dir / "filtered_pkg.tar.gz")
    filtered_tar.write_bytes(sub_tar_buf.getvalue())
    extract_tar_safely(filtered_tar, extracted_root)
    return ensure_contained_path(extracted_root, extracted_root / target_dir_name)


def deploy_cloud_run_via_rest_apis(
    pkg_dir: Path,
    service_name: str,
    model_slug: str,
    project_id: str,
    region: str,
    staging_bucket: str,
    gcs_client: storage.Client | None = None,
) -> str:
    """Build container via Cloud Build REST API and deploy via Cloud Run Admin v2 REST API (zero `gcloud` CLI)."""
    token = _get_gcp_token()
    ts = int(time.time())
    src_object = f"cloudbuild/{service_name}-{ts}.tar.gz"
    image_uri = f"{region}-docker.pkg.dev/{project_id}/cloud-run-source-deploy/{service_name}:v{ts}"

    # 1. Upload sanitized package tarball to GCS staging bucket
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for file_path in sorted(pkg_dir.rglob("*")):
            if file_path.is_file() and "__pycache__" not in file_path.parts:
                rel = file_path.relative_to(pkg_dir).as_posix()
                data = file_path.read_bytes()
                ti = tarfile.TarInfo(name=rel)
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))

    client = gcs_client or storage.Client(project=project_id)
    client.bucket(staging_bucket).blob(src_object).upload_from_string(
        buf.getvalue(),
        content_type="application/gzip",
    )

    # 2. Trigger Cloud Build REST API
    cb_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/locations/{region}/builds"
    cb_op = _gcp_json_request(
        "POST",
        cb_url,
        token,
        project_id,
        payload={
            "source": {"storageSource": {"bucket": staging_bucket, "object": src_object}},
            "steps": [
                {
                    "name": "gcr.io/cloud-builders/docker",
                    "args": ["build", "-t", image_uri, "."],
                }
            ],
            "images": [image_uri],
        },
    )
    op_name = str(cb_op.get("name") or "")
    for _ in range(120):
        if cb_op.get("done"):
            break
        time.sleep(5.0)
        cb_op = _gcp_json_request(
            "GET",
            f"https://cloudbuild.googleapis.com/v1/{op_name}",
            token,
            project_id,
        )
    if not cb_op.get("done") or "error" in cb_op:
        raise RuntimeError(f"Cloud Build failed for {service_name}: {cb_op.get('error')}")

    # 3. Upsert Cloud Run v2 Service
    parent = f"projects/{project_id}/locations/{region}"
    svc_res_name = f"{parent}/services/{service_name}"
    svc_url = f"https://run.googleapis.com/v2/{svc_res_name}"
    svc_body: dict[str, Any] = {
        "labels": {"datacloud": "antigravity", "model": model_slug},
        "template": {
            "containers": [
                {
                    "image": image_uri,
                    "ports": [{"containerPort": 8080}],
                    "env": [{"name": "GOOGLE_CLOUD_PROJECT", "value": project_id}],
                }
            ]
        },
    }

    exists = False
    try:
        _gcp_json_request("GET", svc_url, token, project_id)
        exists = True
    except RuntimeError:
        exists = False

    if exists:
        run_op = _gcp_json_request("PATCH", svc_url, token, project_id, payload=svc_body)
    else:
        create_url = f"https://run.googleapis.com/v2/{parent}/services?serviceId={service_name}"
        run_op = _gcp_json_request("POST", create_url, token, project_id, payload=svc_body)

    run_op_name = str(run_op.get("name") or "")
    for _ in range(90):
        if run_op.get("done"):
            break
        time.sleep(3.0)
        run_op = _gcp_json_request(
            "GET",
            f"https://run.googleapis.com/v2/{run_op_name}",
            token,
            project_id,
        )
    if not run_op.get("done") or "error" in run_op:
        raise RuntimeError(f"Cloud Run v2 deploy failed for {service_name}: {run_op.get('error')}")

    svc_final = _gcp_json_request("GET", svc_url, token, project_id)
    uri = str(svc_final.get("uri") or "")
    if not uri.startswith("https://"):
        raise RuntimeError(f"Cloud Run v2 service {service_name} missing HTTPS uri: {svc_final}")
    return uri


def _call_agent_registry(
    tool_name: str,
    arguments: dict[str, Any],
    token: str,
    project_id: str,
) -> dict[str, Any]:
    req = urllib.request.Request(
        AGENT_REGISTRY_MCP_URL,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45.0) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"Agent Registry HTTP {exc.code} in {tool_name}: {detail}") from exc

    if "error" in envelope:
        raise RuntimeError(f"Agent Registry RPC error in {tool_name}: {envelope['error']}")
    res = envelope.get("result") or {}
    if res.get("isError"):
        raise RuntimeError(f"Agent Registry tool error in {tool_name}: {res.get('content')}")
    if isinstance(res.get("structuredContent"), dict) and res["structuredContent"]:
        return res["structuredContent"]
    txt = "\n".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict)).strip()
    return json.loads(txt) if txt.startswith("{") else {"raw": txt}


def _zip_skill_directory_b64(skill_dir: Path) -> tuple[str, dict[str, Any]]:
    md_path = skill_dir / "SKILL.md"
    raw_txt = md_path.read_text(encoding="utf-8")
    parts = raw_txt.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Missing YAML frontmatter in {md_path}")
    fm = yaml.safe_load(parts[1])
    if not isinstance(fm, dict) or not fm.get("name") or not fm.get("description"):
        raise ValueError(f"SKILL.md frontmatter missing name/description in {md_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(skill_dir.rglob("*")):
            if entry.is_file() and not entry.name.startswith("."):
                zf.writestr(entry.relative_to(skill_dir).as_posix(), entry.read_bytes())
    return base64.b64encode(buf.getvalue()).decode("ascii"), fm


def _fetch_remote_mcp_tools(cloud_run_url: str) -> list[dict[str, Any]]:
    """Query `tools/list` on the newly deployed Cloud Run MCP service to register exact tool specs."""
    mcp_url = f"{cloud_run_url.rstrip('/')}/mcp"
    if not mcp_url.startswith("https://"):
        raise ValueError(f"Cloud Run URL must use HTTPS: {cloud_run_url!r}")
    req = urllib.request.Request(
        mcp_url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        envelope = json.loads(resp.read().decode("utf-8"))
    tools = (envelope.get("result") or {}).get("tools")
    return tools if isinstance(tools, list) else []


def publish_twin_to_agent_registry(
    pkg_dir: Path,
    model_slug: str,
    cloud_run_url: str,
    registry_project_id: str,
    registry_location: str = "global",
) -> tuple[str, list[str]]:
    """Register `<slug>-bq-twin-mcp` and all `skills/*/SKILL.md` in Agent Registry."""
    safe_slug = validate_model_slug(model_slug)
    proj = validate_safe_identifier(registry_project_id, "registry_project_id")
    loc = validate_safe_identifier(registry_location, "registry_location")
    service_id = f"{safe_slug}-bq-twin-mcp"
    parent = f"projects/{proj}/locations/{loc}"
    service_name = f"{parent}/services/{service_id}"

    token = _get_gcp_token()
    tools = _fetch_remote_mcp_tools(cloud_run_url)
    svc_body: dict[str, Any] = {
        "displayName": service_id,
        "description": f"Isolated BigQuery Digital Twin Remote MCP Server for {safe_slug}",
        "interfaces": [{"protocolBinding": "JSONRPC", "url": f"{cloud_run_url.rstrip('/')}/mcp"}],
        "mcpServerSpec": {"type": "TOOL_SPEC", "content": {"tools": tools}},
    }

    existing = _call_agent_registry("list_services", {"parent": parent}, token, proj).get("services") or []
    has_svc = any(str(s.get("name", "")).endswith(f"/services/{service_id}") for s in existing)
    if has_svc:
        _call_agent_registry(
            "update_service",
            {
                "service": {"name": service_name, **svc_body},
                "updateMask": "displayName,description,interfaces,mcpServerSpec",
            },
            token,
            proj,
        )
        svc_action = "updated"
    else:
        _call_agent_registry(
            "create_service",
            {"parent": parent, "serviceId": service_id, "service": svc_body},
            token,
            proj,
        )
        svc_action = "created"

    published_skills: list[str] = []
    skills_root = pkg_dir / "skills"
    if skills_root.exists():
        for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()):
            sid = validate_model_slug(skill_dir.name)
            zb64, fm = _zip_skill_directory_b64(skill_dir)
            desc = str(fm["description"])[:2000]
            priv_name = f"{parent}/skills/private-{sid}"
            try:
                existing_sk = _call_agent_registry("get_skill", {"name": priv_name}, token, proj)
            except (RuntimeError, ValueError, OSError):
                existing_sk = None

            if existing_sk is None:
                _call_agent_registry(
                    "create_skill",
                    {
                        "parent": parent,
                        "skillId": sid,
                        "skill": {
                            "displayName": sid,
                            "description": desc,
                            "type": "SIMPLE",
                            "targetState": "TARGET_STATE_ACTIVE",
                            "initialRevision": {"archiveUploadSource": {"archiveContent": zb64}},
                        },
                    },
                    token,
                    proj,
                )
            else:
                rev_id = f"rev-{int(time.time())}"
                _call_agent_registry(
                    "create_skill_revision",
                    {
                        "parent": priv_name,
                        "skillRevisionId": rev_id,
                        "skillRevision": {"archiveUploadSource": {"archiveContent": zb64}},
                    },
                    token,
                    proj,
                )
                _call_agent_registry(
                    "update_skill",
                    {
                        "skill": {
                            "name": priv_name,
                            "displayName": sid,
                            "description": desc,
                            "type": "SIMPLE",
                            "targetState": "TARGET_STATE_ACTIVE",
                            "defaultRevision": f"{priv_name}/revisions/{rev_id}",
                        },
                        "updateMask": "displayName,description,targetState,defaultRevision",
                    },
                    token,
                    proj,
                )
            published_skills.append(sid)

    return svc_action, published_skills


def deploy_onboarded_model(
    repo_root: Path,
    model_slug: str,
    skip_bqml: bool = False,
    pr_number: int | None = None,
    require_merged_pr: bool = False,
    prefer_rest_deploy: bool = False,
    settings: OnboardingSettings | None = None,
) -> DeploymentSummary:
    """Provision BigQuery Digital Twin + BQML, deploy Cloud Run MCP, and register skills post-PR review."""
    cfg = settings or get_onboarding_settings()
    safe_slug = validate_model_slug(model_slug)
    proj = validate_safe_identifier(cfg.gcp_project_id, "gcp_project_id")
    region = validate_safe_identifier(cfg.gcp_region, "gcp_region")
    reg_proj = validate_safe_identifier(cfg.registry_project_id, "registry_project_id")

    if require_merged_pr:
        if pr_number is None:
            raise ValueError("pr_number is required when require_merged_pr=True.")
        if not verify_pr_merged(cfg.github_repo, pr_number):
            raise RuntimeError(f"Pull Request #{pr_number} is not merged yet; deployment blocked.")

    with tempfile.TemporaryDirectory(prefix=f"onboard_deploy_{safe_slug}_") as tmp_dir:
        resolved_repo = repo_root.expanduser().resolve()
        local_candidate = resolved_repo / f"{safe_slug}-bq-twin"
        if local_candidate.exists():
            pkg_dir = ensure_contained_path(resolved_repo, local_candidate)
        else:
            pkg_dir = fetch_package_from_github_tarball(
                github_repo=cfg.github_repo,
                git_ref=cfg.base_git_branch,
                model_slug=safe_slug,
                scratch_dir=Path(tmp_dir),
            )

        audit_generated_package_tree(pkg_dir)

        dataset_id = f"{safe_slug.replace('-', '_')}_digital_twin"
        service_name = f"{safe_slug}-bq-twin-mcp"

        # 1. Seed BigQuery Digital Twin & train ARIMA_PLUS models
        load_script = ensure_contained_path(pkg_dir, pkg_dir / "scripts" / "load_to_bq.py")
        if not load_script.exists():
            raise FileNotFoundError(f"Missing BigQuery loader script: {load_script}")

        load_cmd = [sys.executable, str(load_script)]
        if skip_bqml:
            load_cmd.append("--skip-bqml")

        load_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "PYTHONPATH": str(pkg_dir / "src"),
            "GOOGLE_CLOUD_PROJECT": proj,
        }
        load_proc = subprocess.run(
            load_cmd,
            cwd=str(pkg_dir),
            env=load_env,
            capture_output=True,
            text=True,
            timeout=900.0,
            check=False,
        )
        if load_proc.returncode != 0:
            raise RuntimeError(f"BigQuery seeding failed:\n{load_proc.stderr[-800:]}")

        # 2. Deploy isolated Cloud Run MCP service (CLI gcloud locally, or Cloud Build + Cloud Run REST APIs on Cloud Run)
        has_gcloud = shutil.which("gcloud") is not None
        if has_gcloud and not prefer_rest_deploy:
            deploy_cmd = [
                "gcloud",
                "run",
                "deploy",
                service_name,
                "--source",
                str(pkg_dir),
                "--project",
                proj,
                "--region",
                region,
                "--labels",
                f"datacloud=antigravity,model={safe_slug}",
                "--quiet",
                "--format=value(status.url)",
            ]
            run_proc = subprocess.run(
                deploy_cmd,
                cwd=str(pkg_dir),
                capture_output=True,
                text=True,
                timeout=900.0,
                check=False,
            )
            if run_proc.returncode != 0:
                raise RuntimeError(f"Cloud Run deploy failed:\n{run_proc.stderr[-800:]}")
            lines = [ln.strip() for ln in run_proc.stdout.splitlines() if ln.strip().startswith("https://")]
            if not lines:
                raise RuntimeError(f"Cloud Run did not return a valid HTTPS URL: {run_proc.stdout!r}")
            cloud_run_url = lines[-1]
        else:
            cloud_run_url = deploy_cloud_run_via_rest_apis(
                pkg_dir=pkg_dir,
                service_name=service_name,
                model_slug=safe_slug,
                project_id=proj,
                region=region,
                staging_bucket=cfg.staging_bucket,
            )

        # 3. Publish MCP service + skills to Gemini Enterprise Agent Registry
        mcp_action, skill_ids = publish_twin_to_agent_registry(
            pkg_dir=pkg_dir,
            model_slug=safe_slug,
            cloud_run_url=cloud_run_url,
            registry_project_id=reg_proj,
            registry_location=cfg.registry_location,
        )

    return DeploymentSummary(
        model_slug=safe_slug,
        gcp_project_id=proj,
        bq_dataset_id=dataset_id,
        bqml_trained=not skip_bqml,
        cloud_run_service=service_name,
        cloud_run_url=cloud_run_url,
        registry_project_id=reg_proj,
        mcp_service_action=mcp_action,
        published_skills=skill_ids,
    )
