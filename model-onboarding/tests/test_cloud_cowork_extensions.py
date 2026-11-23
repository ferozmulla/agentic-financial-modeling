"""Tests for Cloud Run & Cowork repo-free extensions: `+` uploads, GitHub Git Data API, Cloud Run REST deploy, and Cowork installer isolation."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any, Self

import pytest
from fastapi.testclient import TestClient

from model_onboarding.config import OnboardingSettings
from model_onboarding.controller import OnboardingController
from model_onboarding.deployer import deploy_cloud_run_via_rest_apis, fetch_package_from_github_tarball
from model_onboarding.hygiene_gate import evaluate_workbook_hygiene
from model_onboarding.mcp_app import create_onboarding_mcp_app
from model_onboarding.mcp_tools import OnboardingMcpDispatcher
from model_onboarding.models import ParityVerificationReport
from model_onboarding.pr_publisher import publish_onboarding_branch_and_pr
from scripts.install_onboarding_cowork import configure_onboarding_in_cowork
from tests.test_sandbox_worker_and_sanitizer import _build_valid_generated_twin, _make_seed_xlsx


def test_cowork_plus_upload_and_binary_validation(tmp_path: Path) -> None:
    seed = _make_seed_xlsx(tmp_path / "CoworkAttached.xlsx")
    settings = OnboardingSettings(
        gcp_project_id="offline-test",
        local_jobs_dir=tmp_path / "jobs",
    )
    ctrl = OnboardingController(repo_root=tmp_path / "no_git_repo", settings=settings)
    dispatcher = OnboardingMcpDispatcher(controller=ctrl, settings=settings)
    app = create_onboarding_mcp_app(dispatcher=dispatcher, upload_to_gcs=False)
    client = TestClient(app, base_url="http://127.0.0.1:8080")

    # 1. Mint upload URL via MCP tool
    upl_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "create_workbook_upload_url",
                "arguments": {"filename": "CoworkAttached.xlsx"},
            },
        },
    )
    assert upl_resp.status_code == 200
    upl_info = upl_resp.json()["result"]["structuredContent"]
    upload_id = upl_info["upload_id"]
    assert upl_info["direct_post_url"].endswith(f"/v1/uploads/{upload_id}/CoworkAttached.xlsx")

    # 2. Reject non-OpenXML bytes uploaded to /v1/uploads
    bad_post = client.post(
        f"/v1/uploads/{upload_id}/CoworkAttached.xlsx",
        content=b"NOT_AN_EXCEL_ARCHIVE",
    )
    assert bad_post.status_code == 400

    # 3. Accept valid .xlsx binary and immediately run Stage 1 assessment on returned workbook_uri
    good_post = client.post(
        f"/v1/uploads/{upload_id}/CoworkAttached.xlsx",
        content=seed.read_bytes(),
    )
    assert good_post.status_code == 201
    staged_uri = good_post.json()["workbook_uri"]

    assess_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "assess_workbook_onboarding_readiness",
                "arguments": {"workbook_uri": staged_uri, "model_slug": "cowork-attached"},
            },
        },
    )
    assert assess_resp.status_code == 200
    sc = assess_resp.json()["result"]["structuredContent"]["hygiene_report"]
    assert sc["model_slug"] == "cowork-attached"
    assert sc["decision"] in {"GO", "CONDITIONAL_GO"}


def test_repo_free_github_git_data_api_pr_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_non_git_dir = tmp_path / "stateless_cloudrun_dir"
    empty_non_git_dir.mkdir()

    seed = _make_seed_xlsx(tmp_path / "HydroPlant.xlsx")
    hygiene = evaluate_workbook_hygiene(seed, model_slug="hydro-plant")
    pkg = _build_valid_generated_twin(tmp_path / "hydro-plant-bq-twin", slug="hydro-plant")
    parity = ParityVerificationReport(
        model_slug="hydro-plant",
        passed=True,
        pytest_passed=2,
        total_compared_cells=50,
        total_matched_cells=50,
        parity_rate_pct=100.0,
        verified_locally=True,
    )

    monkeypatch.setenv("ONBOARD_GITHUB_TOKEN", "ghp_mock_ephemeral_token")
    monkeypatch.setattr(
        "model_onboarding.pr_publisher.archive_seed_to_vault",
        lambda *a, **kw: "gs://comm-model-mod-sheets-mod-artifacts/golden-seed/hydro-plant/HydroPlant.xlsx",
    )

    api_calls: list[tuple[str, str]] = []

    def _fake_gh_api(
        method: str,
        github_repo: str,
        subpath: str,
        token: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del github_repo, token
        api_calls.append((method, subpath))
        if subpath == "git/ref/heads/main":
            return {"object": {"sha": "base_commit_111"}}
        if subpath == "git/commits/base_commit_111":
            return {"tree": {"sha": "base_tree_222"}}
        if subpath == "git/blobs":
            return {"sha": "blob_sha_333"}
        if subpath == "git/trees":
            assert payload is not None
            paths = [entry["path"] for entry in payload["tree"]]
            assert any(p.endswith("reports/hygiene_exception_report.md") for p in paths)
            assert any(p.endswith("reports/parity_verification_report.md") for p in paths)
            assert not any(p.endswith((".xlsx", ".xlsm")) for p in paths)
            return {"sha": "new_tree_444"}
        if subpath == "git/commits":
            return {"sha": "new_commit_555"}
        if subpath == "git/refs":
            return {"ref": payload["ref"] if payload else ""}
        if subpath == "pulls":
            return {
                "html_url": "https://github.com/ferozmulla/agentic-financial-modeling/pull/88",
                "number": 88,
            }
        raise AssertionError(f"Unexpected GitHub API subpath: {subpath}")

    monkeypatch.setattr("model_onboarding.pr_publisher._github_api_request", _fake_gh_api)

    res = publish_onboarding_branch_and_pr(
        repo_root=empty_non_git_dir,
        job_id="job-cloud99",
        sanitized_pkg_dir=pkg,
        xlsx_path=seed,
        hygiene=hygiene,
        parity=parity,
        local_only=False,
    )
    assert res.commit_sha == "new_commit_555"
    assert res.pr_number == 88
    assert res.pr_url.endswith("/pull/88")
    assert ("POST", "pulls") in api_calls


def test_repo_free_github_tarball_fetch_and_cloud_run_rest_deploy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_src = _build_valid_generated_twin(tmp_path / "src_pkg", slug="solar-park")
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        for fp in sorted(pkg_src.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(pkg_src).as_posix()
                data = fp.read_bytes()
                ti = tarfile.TarInfo(name=f"ferozmulla-repo-abc1234/solar-park-bq-twin/{rel}")
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))

    class _FakeHttpResp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=60.0: _FakeHttpResp(tar_buf.getvalue()),
    )

    extracted_pkg = fetch_package_from_github_tarball(
        github_repo="ferozmulla/agentic-financial-modeling",
        git_ref="main",
        model_slug="solar-park",
        scratch_dir=tmp_path / "dl",
    )
    assert (extracted_pkg / "Dockerfile").exists()
    assert (extracted_pkg / "scripts" / "load_to_bq.py").exists()

    # Now test gcloud-free Cloud Build + Cloud Run v2 REST deployment
    class _FakeBlob:
        def upload_from_string(self, data: bytes, content_type: str = "") -> None:
            assert len(data) > 0
            assert content_type == "application/gzip"

    class _FakeBucket:
        def blob(self, name: str) -> _FakeBlob:
            assert name.startswith("cloudbuild/solar-park-bq-twin-mcp-")
            return _FakeBlob()

    class _FakeGcs:
        def bucket(self, name: str) -> _FakeBucket:
            assert name == "comm-model-mod-onboarding-staging"
            return _FakeBucket()

    monkeypatch.setattr("model_onboarding.deployer._get_gcp_token", lambda: "ya29.mock")
    gcp_calls: list[tuple[str, str]] = []

    def _fake_gcp_json(
        method: str,
        url: str,
        token: str,
        project_id: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 45.0,
    ) -> dict[str, Any]:
        del token, project_id, payload, timeout
        gcp_calls.append((method, url))
        if "cloudbuild.googleapis.com" in url and method == "POST":
            return {"name": "operations/build/123", "done": True}
        if url.endswith("/services/solar-park-bq-twin-mcp") and method == "GET":
            if sum(1 for m, u in gcp_calls if u == url and m == "GET") == 1:
                raise RuntimeError("404 Not Found")
            return {"uri": "https://solar-park-bq-twin-mcp-uc.a.run.app"}
        if "services?serviceId=solar-park-bq-twin-mcp" in url and method == "POST":
            return {"name": "projects/comm-model-mod/locations/us-central1/operations/op1", "done": True}
        raise AssertionError(f"Unexpected GCP REST call: {method} {url}")

    monkeypatch.setattr("model_onboarding.deployer._gcp_json_request", _fake_gcp_json)

    uri = deploy_cloud_run_via_rest_apis(
        pkg_dir=extracted_pkg,
        service_name="solar-park-bq-twin-mcp",
        model_slug="solar-park",
        project_id="comm-model-mod",
        region="us-central1",
        staging_bucket="comm-model-mod-onboarding-staging",
        gcs_client=_FakeGcs(),  # type: ignore[arg-type]
    )
    assert uri == "https://solar-park-bq-twin-mcp-uc.a.run.app"


def test_install_onboarding_cowork_preserves_brazil_and_eulr_intact(tmp_path: Path) -> None:
    cowork_cfg = tmp_path / "config"
    (cowork_cfg / "skills" / "brazil-power-model-gcp").mkdir(parents=True)
    (cowork_cfg / "skills" / "eulr-refining-model-gcp").mkdir(parents=True)

    brazil_md = "---\nname: brazil-power-model-gcp\n---\n# Brazil\n"
    eulr_md = "---\nname: eulr-refining-model-gcp\n---\n# EULR\n"
    (cowork_cfg / "skills" / "brazil-power-model-gcp" / "SKILL.md").write_text(brazil_md, encoding="utf-8")
    (cowork_cfg / "skills" / "eulr-refining-model-gcp" / "SKILL.md").write_text(eulr_md, encoding="utf-8")

    initial_mcp = {
        "mcpServers": {
            "brazil-power-bq-twin-mcp": {"serverUrl": "https://brazil.a.run.app/mcp/sse"},
            "eulr-refining-mcp": {"serverUrl": "https://eulr.a.run.app/mcp/sse"},
        }
    }
    (cowork_cfg / "mcp_config.json").write_text(json.dumps(initial_mcp, indent=2), encoding="utf-8")

    initial_manifest = {
        "skills": {
            "brazil-power-model-gcp": {"status": "installed", "disabled": False, "error": None},
            "eulr-refining-model-gcp": {"status": "installed", "disabled": False, "error": None},
        }
    }
    (cowork_cfg / "skills" / "manifest.json").write_text(
        json.dumps(initial_manifest, indent=2),
        encoding="utf-8",
    )

    # 1. Enable model-onboarding-mcp
    res_on = configure_onboarding_in_cowork(
        config_dir=cowork_cfg,
        server_sse_url="https://model-onboarding-mcp-uc.a.run.app",
        enable=True,
    )
    assert sorted(res_on["mcp_servers_present"]) == [
        "brazil-power-bq-twin-mcp",
        "eulr-refining-mcp",
        "model-onboarding-mcp",
    ]
    assert (cowork_cfg / "skills" / "onboard-energy-model-gcp" / "SKILL.md").is_file()
    assert (cowork_cfg / "skills" / "brazil-power-model-gcp" / "SKILL.md").read_text(encoding="utf-8") == brazil_md
    assert (cowork_cfg / "skills" / "eulr-refining-model-gcp" / "SKILL.md").read_text(encoding="utf-8") == eulr_md

    # 2. Disable model-onboarding-mcp -> Brazil & EULR remain byte-for-byte intact
    configure_onboarding_in_cowork(
        config_dir=cowork_cfg,
        server_sse_url="https://model-onboarding-mcp-uc.a.run.app",
        enable=False,
    )
    after_mcp = json.loads((cowork_cfg / "mcp_config.json").read_text(encoding="utf-8"))
    assert after_mcp == initial_mcp
    after_manifest = json.loads((cowork_cfg / "skills" / "manifest.json").read_text(encoding="utf-8"))
    assert after_manifest == initial_manifest
