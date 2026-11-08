from pathlib import Path
from brazil_power_agent.session_store import BrazilPowerSessionManager


def test_session_assumptions_and_analysis_rendering(tmp_path: Path) -> None:
    mgr = BrazilPowerSessionManager(session_path=tmp_path / "session.json")
    base = mgr.get_assumptions(technologies=["_01_CF", "_06_CF"])
    assert "General!C20" in base["inline_excel_table_md"] or "Fuel" in base["inline_excel_table_md"]
    assert "Col C" in base["full_artifact_table_md"]

    upd = mgr.update_assumptions(
        overrides={"General!C20": 6.50, "General!H14": 2.0},
        reset_to_baseline=False,
    )
    assert upd["modified_count"] == 2
    assert "6.50" in upd["diff_table_md"]

    tornado = mgr.run_tornado(technology_code="_06_CF")
    assert "_06_CF" in tornado["inline_excel_table_md"]
    assert "series" in tornado["echarts_spec"]

    lcoe = mgr.run_lcoe_horizon()
    assert "Output_3" in lcoe["inline_excel_table_md"]
    assert "2024" in lcoe["full_artifact_table_md"]
    assert "2046" in lcoe["full_artifact_table_md"]

    dcf = mgr.run_dcf(technology_code="_01_CF")
    assert "_01_CF" in dcf["inline_summary_table_md"]
    assert "2053" in dcf["full_artifact_table_md"]
    assert "series" in dcf["echarts_spec"]


def test_session_bqml_cvu_sweep_nested_overrides_and_persistence(tmp_path: Path) -> None:
    session_file = tmp_path / "persisted_session.json"
    mgr = BrazilPowerSessionManager(session_path=session_file)

    upd = mgr.update_assumptions(
        overrides={
            "_01_CF": {"fuel_cost_r_per_mmbtu": 6.50, "real_wacc": 0.09},
            "_06_CF": {"lead_time_years": 2.0},
        },
        reset_to_baseline=False,
    )
    assert upd["modified_count"] == 3
    assert mgr.cell_overrides["General!C20"] == 6.50
    assert mgr.cell_overrides["General!C34"] == 0.09
    assert mgr.cell_overrides["General!H14"] == 2.0

    bqml = mgr.run_bqml_refresh(curve_types=["CAPEX", "FUEL", "CF"])
    assert "LT Capex" in bqml["inline_excel_table_md"]
    assert "2046" in bqml["full_artifact_table_md"]
    assert "series" in bqml["echarts_spec"]

    cvu = mgr.run_cvu_sweep(technology_code="_01_CF")
    assert "calculo_cvu1" in cvu["inline_excel_table_md"]
    assert len(cvu["sweep_rows"]) == 10
    assert "series" in cvu["echarts_spec"]

    # Reload from disk and verify persistence
    reloaded = BrazilPowerSessionManager(session_path=session_file)
    assert reloaded.cell_overrides["General!C20"] == 6.50
    assert "_01_CF!C70" in reloaded.get_all_cell_writes()

    # Reset to baseline
    rst = reloaded.update_assumptions(overrides={}, reset_to_baseline=True)
    assert rst["modified_count"] == 0
    assert reloaded.cell_overrides == {}
