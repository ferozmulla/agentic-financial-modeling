from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx

from portfolio_assessment.reference_resolver import (
    classify_link_target_syntactic,
    resolve_workbook_external_links,
)
from portfolio_assessment.xml_inspector import scan_workbook_openxml


def test_syntactic_link_classification_tiers() -> None:
    tier_clean, sc_clean = classify_link_target_syntactic(
        "https://spgl.sharepoint.com/sites/Downstream_HOU/Job/LONGTERM/LR202409/Uslr202409.xlsx",
        host_vintage="202409",
    )
    assert tier_clean == "CLEAN_CORPORATE_LINK"
    assert sc_clean == 1.0

    tier_drift, sc_drift = classify_link_target_syntactic(
        "https://spgl.sharepoint.com/sites/Downstream_HOU/Job/LONGTERM/LR202406/Uslr202406.xlsx",
        host_vintage="202409",
    )
    assert tier_drift == "PRIOR_VINTAGE_DRIFT"
    assert sc_drift == 0.5

    tier_ghost, sc_ghost = classify_link_target_syntactic(
        "file:///C:\\Users\\analyst\\Downloads\\Inputs.xlsx",
        host_vintage="202409",
    )
    assert tier_ghost == "GHOST_OR_LOCAL_PATH"
    assert sc_ghost == 0.0


def test_live_reference_roots_confirms_exact_and_drifted_peer_cells(tmp_path: Path) -> None:
    ref_dir = tmp_path / "onedrive_sp_sync"
    ref_dir.mkdir()
    build_synthetic_xlsx(
        ref_dir / "Uslr202409.xlsx",
        sheets={"Links Out": [{"r": "B2", "v": "100.0"}, {"r": "C2", "v": "105.0"}]},
    )

    host_path = build_synthetic_xlsx(
        tmp_path / "Eulr202409.xlsx",
        sheets={
            "Input": [
                {"r": "B2", "f": "'[1]Links Out'!$B$2", "v": "100.0"},
                {"r": "C2", "f": "'[1]Links Out'!$C$2", "v": "100.0"},  # drifted vs 105.0 in peer!
            ]
        },
        external_links=["https://spgl.sharepoint.com/sites/Downstream_HOU/LR202409/Uslr202409.xlsx"],
    )

    scan = scan_workbook_openxml(host_path)
    audits = resolve_workbook_external_links(scan, reference_roots=[ref_dir])
    assert len(audits) == 1
    rec = audits[0]
    assert rec.resolution_status == "CONFIRMED_STALE_CACHE_DRIFT"
    assert rec.exact_match_cells == 1
    assert rec.drifted_cells == 1
    assert rec.max_rel_drift > 0.04
