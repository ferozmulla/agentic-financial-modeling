"""Tests for Stage 2 Sandbox Output Sanitizer, AST Guard, Local Pytest Verifier, and Managed Agents Worker."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from model_onboarding.config import OnboardingSettings
from model_onboarding.hygiene_gate import evaluate_workbook_hygiene
from model_onboarding.models import ParityVerificationReport
from model_onboarding.sandbox_worker import ManagedAgentsSandboxWorker, parse_interactions_sse_stream
from model_onboarding.sanitizer import (
    audit_generated_package_tree,
    extract_tar_safely,
    run_local_parity_pytest,
)


def _build_valid_generated_twin(pkg_dir: Path, slug: str = "mini-grid") -> Path:
    pkg_name = f"{slug.replace('-', '_')}_bq_twin"
    (pkg_dir / "src" / pkg_name).mkdir(parents=True, exist_ok=True)
    (pkg_dir / "tests").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "skills" / f"{slug}-model-gcp").mkdir(parents=True, exist_ok=True)

    (pkg_dir / "Dockerfile").write_text(
        f'FROM python:3.11-slim\nCOPY src /app/src\nCMD ["uvicorn", "{pkg_name}.mcp_app:app"]\n',
        encoding="utf-8",
    )
    (pkg_dir / "pyproject.toml").write_text(
        f'[project]\nname = "{slug}-bq-twin"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (pkg_dir / "README.md").write_text(f"# {slug}\n", encoding="utf-8")
    (pkg_dir / "src" / pkg_name / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "src" / pkg_name / "solver_engine.py").write_text(
        "def solve_total(a: float, b: float) -> float:\n    return a + b\n",
        encoding="utf-8",
    )
    (pkg_dir / "scripts" / "load_to_bq.py").write_text("print('ok')\n", encoding="utf-8")
    (pkg_dir / "skills" / f"{slug}-model-gcp" / "SKILL.md").write_text(
        f'---\nname: {slug}-model-gcp\ndescription: "Test skill"\n---\n# Skill\n',
        encoding="utf-8",
    )
    (pkg_dir / "tests" / "test_parity.py").write_text(
        "import os\nimport openpyxl\n"
        f"from {pkg_name}.solver_engine import solve_total\n\n"
        "def test_seed_parity():\n"
        "    wb = openpyxl.load_workbook(os.environ['ONBOARD_SEED_WORKBOOK_PATH'], data_only=True)\n"
        "    ws = wb['Model']\n"
        "    assert abs(solve_total(float(ws['A1'].value), float(ws['A2'].value)) - float(ws['A3'].value)) < 1e-6\n",
        encoding="utf-8",
    )
    return pkg_dir


def _make_seed_xlsx(path: Path) -> Path:
    import re
    import zipfile

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Model"
    ws["A1"] = 12.5
    ws["A2"] = 7.5
    ws["A3"] = "=A1+A2"
    wb.save(path)

    patched = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)
            if item.filename.endswith("sheet1.xml"):
                txt = raw.decode("utf-8")
                txt = re.sub(r"(<f[^>]*>A1\+A2</f>)", r"\1<v>20.0</v>", txt)
                raw = txt.encode("utf-8")
            zout.writestr(item, raw)
    patched.replace(path)
    return path


def test_extract_tar_safely_blocks_traversal_and_symlinks(tmp_path: Path) -> None:
    evil_tar = tmp_path / "evil.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="../escaped.py")
        payload = b"print('escaped')\n"
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    evil_tar.write_bytes(buf.getvalue())

    with pytest.raises(ValueError, match="Unsafe tar member path"):
        extract_tar_safely(evil_tar, tmp_path / "dest")

    sym_tar = tmp_path / "sym.tar.gz"
    buf2 = io.BytesIO()
    with tarfile.open(fileobj=buf2, mode="w:gz") as tf:
        sinfo = tarfile.TarInfo(name="pkg/link")
        sinfo.type = tarfile.SYMTYPE
        sinfo.linkname = "/etc/passwd"
        tf.addfile(sinfo)
    sym_tar.write_bytes(buf2.getvalue())

    with pytest.raises(ValueError, match="Disallowed special/symlink"):
        extract_tar_safely(sym_tar, tmp_path / "dest2")


def test_sanitizer_blocks_xlsm_secrets_and_eval_then_passes_clean_pkg(tmp_path: Path) -> None:
    pkg = _build_valid_generated_twin(tmp_path / "mini-grid-bq-twin")

    # 1. Leak an .xlsm file -> blocked
    leaked_xlsm = pkg / "leaked.xlsm"
    leaked_xlsm.write_bytes(b"PK\x03\x04")
    with pytest.raises(ValueError, match="Disallowed binary or workbook"):
        audit_generated_package_tree(pkg)
    leaked_xlsm.unlink()

    # 2. Leak a service-account JSON -> blocked
    cred_file = pkg / "service-account-prod.json"
    cred_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Disallowed secret/credential"):
        audit_generated_package_tree(pkg)
    cred_file.unlink()

    # 3. Inject eval() into solver -> blocked
    bad_py = pkg / "src" / "mini_grid_bq_twin" / "bad.py"
    bad_py.write_text("def run(x):\n    return eval(x)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Disallowed dynamic execution call 'eval\\(\\)'"):
        audit_generated_package_tree(pkg)
    bad_py.unlink()

    # 4. Clean package passes both AST audit and local parity pytest
    checked = audit_generated_package_tree(pkg)
    assert len(checked) >= 6

    seed = _make_seed_xlsx(tmp_path / "seed.xlsx")
    initial_report = ParityVerificationReport(
        model_slug="mini-grid",
        passed=True,
        pytest_passed=1,
        total_compared_cells=1,
        total_matched_cells=1,
        parity_rate_pct=100.0,
    )
    verified = run_local_parity_pytest(pkg, seed, initial_report)
    assert verified.verified_locally is True


def test_managed_agents_sse_parser_and_repair_turn_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sse_lines = [
        "event: interaction.delta",
        'data: {"delta": "working"}',
        "event: interaction.complete",
        'data: {"interaction": {"id": "int_001", "environment_id": "env_abc", "status": "completed"}}',
    ]
    inter_id, env_id, st = parse_interactions_sse_stream(sse_lines)
    assert inter_id == "int_001"
    assert env_id == "env_abc"
    assert st == "completed"

    seed = _make_seed_xlsx(tmp_path / "MiniGrid.xlsx")
    hygiene = evaluate_workbook_hygiene(seed, model_slug="mini-grid")
    settings = OnboardingSettings(max_repair_turns=2)
    worker = ManagedAgentsSandboxWorker(settings=settings, gcs_client=object())  # type: ignore[arg-type]

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(worker, "_stage_job_inputs", lambda *a, **kw: "gs://mock-bucket/jobs/job-1")

    def _fake_invoke(
        prompt_text: str,
        job_gcs_uri: str,
        previous_interaction_id: str = "",
        environment_id: str = "",
    ) -> tuple[str, str, str]:
        calls.append(
            {
                "prev": previous_interaction_id,
                "env": environment_id,
                "gcs": job_gcs_uri,
                "prompt": prompt_text,
            }
        )
        turn = len(calls)
        return (f"int_{turn}", "env_shared_99", "completed")

    def _fake_download(
        job_id: str, model_slug: str, download_dir: Path
    ) -> tuple[Path, ParityVerificationReport | None]:
        pkg = _build_valid_generated_twin(download_dir / f"{model_slug}-bq-twin", slug=model_slug)
        # First turn simulates failed parity; second turn (repair turn #1) succeeds
        passed = len(calls) >= 2
        rep = ParityVerificationReport(
            model_slug=model_slug,
            passed=passed,
            pytest_passed=1 if passed else 0,
            pytest_failed=0 if passed else 1,
            total_compared_cells=1,
            total_matched_cells=1 if passed else 0,
            parity_rate_pct=100.0 if passed else 0.0,
        )
        (download_dir / "parity_report.json").write_text(json.dumps(rep.model_dump()), encoding="utf-8")
        return pkg, rep

    monkeypatch.setattr(worker, "_invoke_interaction", _fake_invoke)
    monkeypatch.setattr(worker, "_download_job_outputs", _fake_download)

    pkg_out, verified_rep = worker.generate_and_verify_twin(
        job_id="job-1",
        xlsx_path=seed,
        hygiene_report=hygiene,
        work_dir=tmp_path / "work",
    )
    assert pkg_out.exists()
    assert len(calls) == 2
    assert calls[0]["prev"] == ""
    assert calls[1]["prev"] == "int_1"
    assert calls[1]["env"] == "env_shared_99"
    assert verified_rep.repair_turns_used == 1
    assert verified_rep.verified_locally is True
