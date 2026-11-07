"""SharePoint-portable Upstream Link Hub supporting eulr_baseline_cached, peer_xlsx, and sharepoint_graph modes."""

from __future__ import annotations

import functools
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.parser.openxml_extractor import (
    WorkbookExtract,
    extract_peer_sheet_values,
    extract_workbook_openxml,
)

LinkHealthTier = Literal["ACTIVE_PEER_MODEL", "SHARED_REFERENCE_DB", "FROZEN_LEGACY_PATH"]
UpstreamSourceMode = Literal["eulr_baseline_cached", "peer_xlsx", "sharepoint_graph"]

PEER_WORKBOOK_MAP: dict[str, str] = {
    "14": "Uslr202409.xlsx",
    "18": "Felr202409.xlsx",
    "19": "Tankerlr202409.xlsx",
}

_PURE_SINGLE_EXT_RE = re.compile(r"^\+?'?\[(\d+)\][^!]+!\$?[A-Z]{1,3}\$?\d+$")


def classify_link_health_tier(link_index: str, target_url: str) -> LinkHealthTier:
    idx_num = int(link_index)
    lower_url = target_url.lower()
    if idx_num <= 13 and ("file:///" in lower_url or "gpmo2007" in lower_url or "2000" in lower_url):
        return "FROZEN_LEGACY_PATH"
    if "new lpd" in lower_url or "sr_model" in lower_url or "mnemonics" in lower_url or "rpline" in lower_url:
        return "SHARED_REFERENCE_DB"
    return "ACTIVE_PEER_MODEL"


@dataclass(frozen=True)
class UpstreamExternalSeriesRecord:
    vintage_tag: str
    link_health_tier: LinkHealthTier
    external_link_idx: str
    sharepoint_url: str
    external_workbook_name: str
    source_sheet: str
    source_cell_a1: str
    target_eulr_sheet: str
    target_cell_a1: str
    baseline_cached_value: float
    peer_live_value: float | None
    is_peer_updated: bool
    formula_text: str


@dataclass(frozen=True)
class UpstreamLinkRegistry:
    vintage_tag: str
    total_declared_links: int
    active_external_workbooks: int
    dormant_legacy_links: int
    total_external_formula_cells: int
    valid_cached_cells: int
    records: list[UpstreamExternalSeriesRecord]
    updated_counts_by_workbook: dict[str, int]
    total_peer_updated_cells: int

    def get_cell_overrides_for_mode(
        self, mode: UpstreamSourceMode
    ) -> dict[tuple[str, str], float]:
        """Return (target_eulr_sheet, target_cell_a1) -> value for the requested upstream mode."""
        if mode == "eulr_baseline_cached":
            return {
                (r.target_eulr_sheet, r.target_cell_a1): r.baseline_cached_value
                for r in self.records
            }
        # In peer_xlsx or sharepoint_graph mode, apply live peer values where updated
        out: dict[tuple[str, str], float] = {}
        for r in self.records:
            val = (
                r.peer_live_value
                if (r.is_peer_updated and r.peer_live_value is not None)
                else r.baseline_cached_value
            )
            out[(r.target_eulr_sheet, r.target_cell_a1)] = val
        return out


@functools.lru_cache(maxsize=2)
def build_upstream_link_registry(
    seed_xlsx_path: Path, references_dir: Path
) -> UpstreamLinkRegistry:
    """Build the 14,162-cell SharePoint-portable upstream link registry and evaluate live peer deltas."""
    wb: WorkbookExtract = extract_workbook_openxml(seed_xlsx_path)

    # Pre-scan only the referenced sheets inside the 3 available peer .xlsx workbooks
    peer_sheet_requests: dict[str, set[str]] = {"14": set(), "18": set(), "19": set()}
    for ref in wb.active_ext_refs:
        if ref.link_index in peer_sheet_requests:
            peer_sheet_requests[ref.link_index].add(ref.ext_sheet.lower())

    peer_caches: dict[str, dict[str, dict[str, float]]] = {}
    for l_idx, peer_fname in PEER_WORKBOOK_MAP.items():
        peer_path = references_dir / peer_fname
        if peer_path.exists() and peer_sheet_requests[l_idx]:
            peer_caches[l_idx] = extract_peer_sheet_values(
                peer_path, tuple(sorted(peer_sheet_requests[l_idx]))
            )

    active_link_indices = {r.link_index for r in wb.active_ext_refs}
    records: list[UpstreamExternalSeriesRecord] = []
    updated_by_wb: dict[str, int] = {fname: 0 for fname in PEER_WORKBOOK_MAP.values()}

    for ref in wb.active_ext_refs:
        raw_url = wb.declared_external_links.get(ref.link_index, "")
        wb_name = posixpath.basename(raw_url.replace("\\", "/")) or f"externalLink{ref.link_index}.xlsx"
        tier = classify_link_health_tier(ref.link_index, raw_url)
        base_val = ref.numeric_value if ref.numeric_value is not None else 0.0

        peer_val: float | None = None
        is_updated = False
        if ref.link_index in peer_caches:
            f_clean = ref.formula_text.strip()
            if _PURE_SINGLE_EXT_RE.match(f_clean):
                p_v = (
                    peer_caches[ref.link_index]
                    .get(ref.ext_sheet.lower(), {})
                    .get(ref.ext_cell)
                )
                if p_v is not None and ref.numeric_value is not None:
                    peer_val = p_v
                    rel_diff = abs(p_v - base_val) / max(abs(base_val), 1e-12)
                    if rel_diff > 1e-8:
                        is_updated = True
                        updated_by_wb[PEER_WORKBOOK_MAP[ref.link_index]] += 1

        records.append(
            UpstreamExternalSeriesRecord(
                vintage_tag=wb.vintage_tag or "202409",
                link_health_tier=tier,
                external_link_idx=ref.link_index,
                sharepoint_url=raw_url,
                external_workbook_name=wb_name,
                source_sheet=ref.ext_sheet,
                source_cell_a1=ref.ext_cell,
                target_eulr_sheet=ref.sheet_name,
                target_cell_a1=ref.cell_coord,
                baseline_cached_value=base_val,
                peer_live_value=peer_val,
                is_peer_updated=is_updated,
                formula_text=ref.formula_text,
            )
        )

    return UpstreamLinkRegistry(
        vintage_tag=wb.vintage_tag or "202409",
        total_declared_links=len(wb.declared_external_links),
        active_external_workbooks=len(active_link_indices),
        dormant_legacy_links=len(wb.declared_external_links) - len(active_link_indices),
        total_external_formula_cells=wb.ext_formula_cell_count,
        valid_cached_cells=wb.ext_formula_valid_cache_count,
        records=records,
        updated_counts_by_workbook=updated_by_wb,
        total_peer_updated_cells=sum(updated_by_wb.values()),
    )
