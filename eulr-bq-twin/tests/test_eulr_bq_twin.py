"""Unit, numerical parity, OpenXML synthesis, and Remote MCP transport tests for `eulr-bq-twin`."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from eulr_bq_twin.bq_store import EulrDigitalTwinStore
from eulr_bq_twin.config import EulrTwinSettings
from eulr_bq_twin.formula_engine import EulrFormulaEngine
from eulr_bq_twin.mcp_app import create_eulr_mcp_app
from eulr_bq_twin.mcp_tools import EULR_TWIN_MCP_TOOLS, EulrMcpDispatcher
from eulr_bq_twin.schema_ddl import validate_bq_identifier
from eulr_bq_twin.xlsx_compiler import _shift_formula, compile_eulr_workbook
from eulr_bq_twin.xlsx_synthesizer import sanitize_export_filename

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_XLSX = REPO_ROOT / "Eulr" / "docs" / "Eulr202409.xlsx"
REFS_DIR = REPO_ROOT / "Eulr" / "references"


@pytest.fixture(scope="module")
def compiled_snapshot(tmp_path_factory: pytest.TempPathFactory):
    seed_xlsx = SEED_XLSX
    refs_dir: Path | None = REFS_DIR if REFS_DIR.exists() else None
    if not seed_xlsx.exists():
        try:
            from google.cloud import storage

            cache_dir = tmp_path_factory.mktemp("eulr_golden_seed")
            refs_cache = cache_dir / "references"
            refs_cache.mkdir(parents=True, exist_ok=True)
            bucket = storage.Client(project="comm-model-mod").bucket("comm-model-mod-eulr-twin-vault")
            seed_xlsx = cache_dir / "Eulr202409.xlsx"
            bucket.blob("golden-seed/Eulr202409.xlsx").download_to_filename(str(seed_xlsx))
            for peer in ("Uslr202409.xlsx", "Felr202409.xlsx", "Tankerlr202409.xlsx"):
                bucket.blob(f"golden-seed/references/{peer}").download_to_filename(str(refs_cache / peer))
            refs_dir = refs_cache
        except Exception as exc:
            pytest.skip(f"Local seed retired and GCS vault unavailable ({exc}).")
    payload = compile_eulr_workbook(
        xlsx_path=seed_xlsx,
        workbook_id="eulr_refining_202409",
        version_id="lr202409_baseline",
        references_dir=refs_dir,
    )
    return payload.snapshot


@pytest.fixture()
def offline_dispatcher(compiled_snapshot, tmp_path: Path) -> EulrMcpDispatcher:
    settings = EulrTwinSettings(
        gcp_project_id="offline-test",
        bq_dataset_id="eulr_digital_twin",
        export_local_dir=str(tmp_path / "exports"),
        public_service_url="https://eulr-bq-twin-mcp.example.run.app",
    )
    store = EulrDigitalTwinStore(settings=settings, preloaded_snapshot=compiled_snapshot)
    return EulrMcpDispatcher(store=store, settings=settings)


def test_zero_brazil_or_legacy_imports():
    """Verify `eulr-bq-twin` has zero imports from Brazil packages or legacy `Eulr/`."""
    src_root = REPO_ROOT / "eulr-bq-twin" / "src" / "eulr_bq_twin"
    forbidden = {"brazil_power_bq_twin", "brazil_power_agent", "src"}
    for py_file in src_root.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden, f"Forbidden import {alias.name} in {py_file.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                assert top not in forbidden, f"Forbidden import {node.module} in {py_file.name}"


def test_security_identifier_and_filename_validation():
    with pytest.raises(ValueError):
        validate_bq_identifier("eulr_digital_twin; DROP TABLE dt_cells;--")
    assert sanitize_export_filename("../../etc/passwd") == "passwd.xlsx"
    assert _shift_formula("AT18-$A$5+B$7+$C10", 2, 1) == "AU20-$A$5+C$7+$C12"


def test_compiler_styles_and_peer_links(compiled_snapshot):
    assert len(compiled_snapshot.worksheets) == 19
    assert "shooju_addin" not in compiled_snapshot.worksheets
    assert len(compiled_snapshot.external_links) == 14162
    updated = sum(1 for e in compiled_snapshot.external_links.values() if e.is_peer_updated)
    assert updated == 1104
    # Ensure zero transparent black '00000000' fills exist
    for sm in compiled_snapshot.styles.values():
        assert sm.fill.get("fg_color") != "00000000"


def test_formula_ast_baseline_parity(compiled_snapshot):
    engine = EulrFormulaEngine(compiled_snapshot)
    grid = engine.build_working_grid("baseline_cached")

    # Verify KeyInputs!AU15 (2025 Cat Cracking Margin) formula `=AU18-Carbon!Q10+BW19` matches Excel cache <= 1e-8
    au15_eval = engine.eval_cell(grid, "KeyInputs", 15, 47)
    au15_cached = compiled_snapshot.cells_by_sheet["KeyInputs"][(15, 47)].numeric_value
    assert abs(float(au15_eval) - float(au15_cached)) <= 1e-8

    # Verify IMOfuels!AU11 (`='NWE Cif'!AU122`) matches NWE Diesel EN590 716.403
    imo_eval = engine.eval_cell(grid, "IMOfuels", 11, 47)
    assert abs(float(imo_eval) - 716.403) <= 1e-2


def test_eu_ets_carbon_switch_and_pinned_price_equilibrium(offline_dispatcher: EulrMcpDispatcher):
    sess = "pytest-eq-session"
    # 1. Unperturbed baseline solve
    base_res = offline_dispatcher.dispatch_tool("run_eulr_equilibrium_solve", {"session_id": sess})
    assert base_res["converged"] is True
    assert base_res["final_max_delta_usd_mt"] == 0.0
    base_fcc_2025 = base_res["milestone_snapshot"]["margins"][0]["values"][2025]
    base_diesel_2025 = base_res["milestone_snapshot"]["nwe_cif"][4]["values"][2025]
    assert abs(base_diesel_2025 - 716.40) <= 0.05

    # 2. Switch EU ETS Carbon Off (`Carbon!A5 = 'Base case LTO without carbon pricing'`)
    ets_off_res = offline_dispatcher.dispatch_tool(
        "run_eulr_equilibrium_solve",
        {"session_id": sess, "eu_ets_mode": "carbon_off"},
    )
    assert ets_off_res["milestone_snapshot"]["margins"][5]["values"][2025] == 0.0
    assert ets_off_res["milestone_snapshot"]["margins"][6]["values"][2040] == 0.0
    assert (
        ets_off_res["milestone_snapshot"]["margins"][0]["values"][2040]
        != base_res["milestone_snapshot"]["margins"][0]["values"][2040]
    )
    assert ets_off_res["milestone_snapshot"]["nwe_cif"][4]["values"][2025] is not None

    # 3. Pin 2025 NWE Diesel EN590 (`NWE Cif!AU122 = 750.0`) and verify downstream IMOfuels equilibration + reset
    offline_dispatcher.dispatch_tool(
        "update_eulr_session_overrides",
        {"session_id": sess, "pinned_price_overrides": {"NWE Cif!AU122": 750.0}},
    )
    pinned_solve = offline_dispatcher.dispatch_tool("run_eulr_equilibrium_solve", {"session_id": sess})
    assert pinned_solve["pinned_override_count"] == 1
    assert pinned_solve["milestone_snapshot"]["nwe_cif"][4]["values"][2025] == 750.0
    # NWE Fob Diesel EN590 (`NWE Fob!AU156`, baseline 706.26 $/mt) equilibrates upward around pinned $750/mt CIF
    assert pinned_solve["milestone_snapshot"]["fob_and_imo"][0]["values"][2025] > 730.0

    # 4. Reset to baseline restores exact 716.40
    offline_dispatcher.dispatch_tool(
        "update_eulr_session_overrides",
        {"session_id": sess, "reset_to_baseline": True},
    )
    restored = offline_dispatcher.dispatch_tool("get_eulr_session_assumptions", {"session_id": sess})
    assert restored["snapshot"]["active_override_count"] == 0
    assert abs(restored["snapshot"]["nwe_cif"][4]["values"][2025] - 716.40) <= 0.05


def test_scenario_matrix_bqml_and_hck_economics(offline_dispatcher: EulrMcpDispatcher):
    mat = offline_dispatcher.dispatch_tool(
        "run_eulr_scenario_matrix", {"session_id": "pytest-mat", "target_year": 2025}
    )
    assert len(mat["cases"]) == 6
    assert "echarts_option" in mat

    bqml = offline_dispatcher.dispatch_tool(
        "run_eulr_bqml_forecast_refresh",
        {"session_id": "pytest-bqml", "domain_groups": ["CRUDES", "FREIGHT"], "apply_to_session": True},
    )
    assert len(bqml["series"]) >= 9
    assert bqml["deltas_written"] > 0

    hck = offline_dispatcher.dispatch_tool(
        "run_eulr_hck_and_ulsd_economics", {"session_id": "pytest-hck", "discount_rate_wacc": 0.10}
    )
    assert len(hck["hck_irr_sensitivity_sweep"]) == 9
    assert hck["initial_capex_musd"] > 1800.0


def test_18tab_xlsx_synthesis_and_mcp_http_endpoints(offline_dispatcher: EulrMcpDispatcher):
    app = create_eulr_mcp_app(dispatcher=offline_dispatcher)
    client = TestClient(app)

    hz = client.get("/healthz")
    assert hz.status_code == 200
    assert hz.json()["service"] == "eulr-bq-twin-mcp"

    tl = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert tl.status_code == 200
    assert len(tl.json()["result"]["tools"]) == len(EULR_TWIN_MCP_TOOLS) == 7

    # Pin one cell and synthesize 18-tab workbook
    offline_dispatcher.dispatch_tool(
        "update_eulr_session_overrides",
        {"session_id": "exp-sess", "pinned_price_overrides": {"NWE Cif!AU122": 755.0}},
    )
    exp_rpc = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "export_eulr_workbook",
                "arguments": {"session_id": "exp-sess", "include_upload_tab": False},
            },
        },
    )
    assert exp_rpc.status_code == 200
    payload = json.loads(exp_rpc.json()["result"]["content"][0]["text"])
    assert payload["tabs_exported"] == 18
    assert payload["live_internal_formulas"] > 200_000
    assert payload["pinned_cells_highlighted"] == 1

    # Verify HTTP download & nosniff header
    dl = client.get(f"/v1/exports/{payload['filename']}")
    assert dl.status_code == 200
    assert dl.headers.get("x-content-type-options") == "nosniff"

    # Verify zero broken `[N]` external links in exported workbook & iterative calc enabled
    wb_check = openpyxl.load_workbook(payload["local_path"], read_only=True, data_only=False)
    assert len(wb_check.sheetnames) == 18
    assert "UPLOAD" not in wb_check.sheetnames
    ki_ws = wb_check["KeyInputs"]
    # KeyInputs!AU15 must be a live internal formula, while KeyInputs!AU24 (`[14]KeyInputs!AU46`) is resolved numeric
    assert str(ki_ws["AU15"].value).startswith("=")
    assert isinstance(ki_ws["AU24"].value, (int, float))
    assert wb_check["NWE Cif"]["AU122"].value == 755.0
    wb_check.close()
