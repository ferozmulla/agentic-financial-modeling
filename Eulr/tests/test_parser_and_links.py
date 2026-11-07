"""Phase 1 Verification Tests: TEST-B01 (OpenXML & R1C1 Extraction) and TEST-A05 (External Link Hub & Peer Sync)."""

from __future__ import annotations

from src.core.config import settings
from src.parser.openxml_extractor import extract_workbook_openxml
from src.parser.r1c1_catalog import CIRCULAR_LOOP_SHEETS, build_r1c1_catalog
from src.parser.upstream_link_hub import build_upstream_link_registry


def test_b01_openxml_and_r1c1_extraction() -> None:
    """TEST-B01: Verify exact OpenXML telemetry, 20 sheets, 357,708 formulas, 6,745 CSE arrays, and ULSD-GO circularity."""
    wb = extract_workbook_openxml(settings.resolved_seed_path)

    assert len(wb.sheet_names) == 20
    assert len(wb.active_sheet_names) == 19
    assert wb.retired_hidden_sheets == ["shooju_addin"]
    assert wb.total_c_tags == 604453
    assert wb.total_populated_cells == 438412
    assert wb.total_formula_cells == 357708
    assert wb.total_cse_cells == 6745
    assert wb.calc_pr.get("iterate") == "1"
    assert wb.calc_pr.get("iterateCount") == "10"
    assert len(wb.defined_names) == 2303
    assert len(wb.broken_defined_names) == 281

    catalog = build_r1c1_catalog(settings.resolved_seed_path)
    assert catalog.total_formula_cells == 357708
    assert catalog.unique_r1c1_row_equations == 8028
    assert catalog.cse_formula_cells == 6745

    # Verify ULSD-GO_spread_econs is bidirectionally coupled with NWE Cif & KeyInputs
    assert "ULSD-GO_spread_econs" in CIRCULAR_LOOP_SHEETS
    assert "NWE Cif" in catalog.sheet_dependency_edges["ULSD-GO_spread_econs"]
    assert "ULSD-GO_spread_econs" in catalog.sheet_dependency_edges["KeyInputs"]
    assert "KeyInputs" in catalog.sheet_dependency_edges["NWE Cif"]


def test_a05_upstream_link_hub_and_peer_xlsx_deltas() -> None:
    """TEST-A05: Verify 14,162 external link cells (100% cached) and 1,104 updated cells across Uslr, Felr, and Tankerlr."""
    registry = build_upstream_link_registry(
        settings.resolved_seed_path, settings.resolved_references_dir
    )

    assert registry.total_declared_links == 26
    assert registry.active_external_workbooks == 13
    assert registry.dormant_legacy_links == 13
    assert registry.total_external_formula_cells == 14162
    assert registry.valid_cached_cells == 14162

    # Verify exact live peer delta counts against Uslr202409, Felr202409, and Tankerlr202409
    assert registry.updated_counts_by_workbook["Uslr202409.xlsx"] == 971
    assert registry.updated_counts_by_workbook["Felr202409.xlsx"] == 106
    assert registry.updated_counts_by_workbook["Tankerlr202409.xlsx"] == 27
    assert registry.total_peer_updated_cells == 1104

    cached_map = registry.get_cell_overrides_for_mode("eulr_baseline_cached")
    peer_map = registry.get_cell_overrides_for_mode("peer_xlsx")
    # Input!AU15 is 3.98998 (~3.9900) in cached baseline vs 3.99818 (~3.9982) in Uslr202409.xlsx 'Links Out'!AU13
    assert round(cached_map[("Input", "AU15")], 4) == 3.9900
    assert round(peer_map[("Input", "AU15")], 4) == 3.9982
