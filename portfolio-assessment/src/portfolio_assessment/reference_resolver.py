"""Syntactic link classifier and optional S&P corporate --reference-roots live cell verifier."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.models import ExternalLinkAuditRecord
from portfolio_assessment.xml_inspector import WorkbookScanResult, scan_workbook_openxml

_VINTAGE_RE = re.compile(r"(20\d{4})")
_DIRECT_EXT_CELL_RE = re.compile(r"^=?'?\[\d+\][^!]+'?!\$?[A-Z]{1,3}\$?\d+$")
_GHOST_PATTERNS = re.compile(
    r"(^file:///|[A-Za-z]:\\|^\\\\|-my\.sharepoint\.com/personal/|/Users/|/Downloads/|/Temp/)",
    re.IGNORECASE,
)

PeerLookup = tuple[set[str], dict[tuple[str, str], str | None]]


def classify_link_target_syntactic(raw_target: str, host_vintage: str) -> tuple[str, float]:
    """Classify an external link path into CLEAN_CORPORATE_LINK (1.0), PRIOR_VINTAGE_DRIFT (0.5), or GHOST (0.0)."""
    target = (raw_target or "").strip()
    if not target or _GHOST_PATTERNS.search(target):
        return ("GHOST_OR_LOCAL_PATH", 0.0)

    vintages = _VINTAGE_RE.findall(target)
    if host_vintage and vintages:
        latest_link_vintage = max(vintages)
        if latest_link_vintage < host_vintage:
            return ("PRIOR_VINTAGE_DRIFT", 0.5)

    if "sharepoint.com/sites/" in target.lower() or target.startswith(("/sites/", "../")):
        return ("CLEAN_CORPORATE_LINK", 1.0)

    if "/" not in target and "\\" not in target and target.lower().endswith((".xlsx", ".xlsm", ".xlsb")):
        return ("CLEAN_CORPORATE_LINK", 1.0)

    return ("GHOST_OR_LOCAL_PATH", 0.0)


def _index_reference_files(reference_roots: Sequence[Path]) -> dict[str, Path]:
    by_name: dict[str, Path] = {}
    for root in reference_roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in (".xlsx", ".xlsm", ".xlsb", ".xls"):
            by_name[root.name.lower()] = root
        elif root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm", ".xlsb", ".xls"):
                    by_name.setdefault(p.name.lower(), p)
    return by_name


def _is_within_reference_roots(candidate: Path, reference_roots: Sequence[Path]) -> bool:
    try:
        resolved_cand = candidate.resolve()
    except OSError:
        return False
    for root in reference_roots:
        try:
            resolved_root = root.resolve()
            if resolved_cand == resolved_root or resolved_cand.is_relative_to(resolved_root):
                return True
        except OSError:
            continue
    return False


def _load_peer_lookup(path: Path) -> PeerLookup:
    peer_scan = scan_workbook_openxml(path, values_only=True)
    lookup: dict[tuple[str, str], str | None] = {}
    for ps_name, ps_summary in peer_scan.sheets.items():
        for row_cells in ps_summary.cells_by_row.values():
            for c in row_cells:
                lookup[(ps_name, c.coord)] = c.value
    return (set(peer_scan.sheets.keys()), lookup)


def resolve_workbook_external_links(
    scan: WorkbookScanResult,
    reference_roots: Sequence[Path] = (),
    peer_cache: dict[Path, PeerLookup] | None = None,
) -> list[ExternalLinkAuditRecord]:
    """Audit all declared external links and optionally confirm target sheets/cells via reference_roots."""
    ref_index = _index_reference_files(reference_roots) if reference_roots else {}
    cache = peer_cache if peer_cache is not None else {}

    refs_by_idx = defaultdict(list)
    active_counts: Counter[str] = Counter()
    for ref in scan.active_ext_refs:
        refs_by_idx[ref.link_index].append(ref)
        active_counts[ref.link_index] += 1

    audits: list[ExternalLinkAuditRecord] = []
    wb_name = scan.path.name

    for link_idx, raw_target in sorted(scan.declared_external_links.items(), key=lambda x: int(x[0])):
        tier, syn_score = classify_link_target_syntactic(raw_target, scan.vintage_tag)
        fname = Path(raw_target.replace("\\", "/").split("?")[0]).name
        matched_path = ref_index.get(fname.lower())

        if matched_path is None and reference_roots and raw_target and not raw_target.startswith("http"):
            candidate = Path(raw_target.replace("file:///", ""))
            if (
                _is_within_reference_roots(candidate, reference_roots)
                and candidate.is_file()
                and candidate.suffix.lower() in (".xlsx", ".xlsm", ".xlsb", ".xls")
            ):
                matched_path = candidate

        if not reference_roots:
            audits.append(
                ExternalLinkAuditRecord(
                    workbook_name=wb_name,
                    link_index=link_idx,
                    raw_target=raw_target,
                    link_health_tier=tier,
                    syntactic_score=syn_score,
                    active_formula_refs=active_counts[link_idx],
                    resolution_status="NOT_PROBED_OFFLINE",
                    resolved_local_path="",
                    missing_sheets_count=0,
                    exact_match_cells=0,
                    drifted_cells=0,
                    max_rel_drift=0.0,
                )
            )
            continue

        if matched_path is None:
            audits.append(
                ExternalLinkAuditRecord(
                    workbook_name=wb_name,
                    link_index=link_idx,
                    raw_target=raw_target,
                    link_health_tier=tier,
                    syntactic_score=syn_score,
                    active_formula_refs=active_counts[link_idx],
                    resolution_status="UNRESOLVED_IN_REFERENCE_ROOTS",
                    resolved_local_path="",
                    missing_sheets_count=0,
                    exact_match_cells=0,
                    drifted_cells=0,
                    max_rel_drift=0.0,
                )
            )
            continue

        if matched_path.suffix.lower() in (".xlsb", ".xls"):
            audits.append(
                ExternalLinkAuditRecord(
                    workbook_name=wb_name,
                    link_index=link_idx,
                    raw_target=raw_target,
                    link_health_tier=tier,
                    syntactic_score=syn_score,
                    active_formula_refs=active_counts[link_idx],
                    resolution_status="CONFIRMED_BINARY_FILE_EXISTS",
                    resolved_local_path=str(matched_path),
                    missing_sheets_count=0,
                    exact_match_cells=0,
                    drifted_cells=0,
                    max_rel_drift=0.0,
                )
            )
            continue

        resolved_key = matched_path.resolve()
        if resolved_key not in cache:
            cache[resolved_key] = _load_peer_lookup(matched_path)
        peer_sheets, peer_lookup = cache[resolved_key]

        missing_sheets: set[str] = set()
        exact_cnt = 0
        drift_cnt = 0
        max_drift = 0.0

        for ref in refs_by_idx[link_idx]:
            if ref.ext_sheet not in peer_sheets:
                missing_sheets.add(ref.ext_sheet)
                continue
            if not _DIRECT_EXT_CELL_RE.match(ref.formula_text.strip()):
                continue
            peer_val = peer_lookup.get((ref.ext_sheet, ref.ext_cell))
            if peer_val is None or ref.cached_value is None:
                continue
            try:
                v_host = float(ref.cached_value)
                v_peer = float(peer_val)
                rel = abs(v_host - v_peer) / max(abs(v_host), 1e-9)
                if rel <= 1e-8:
                    exact_cnt += 1
                else:
                    drift_cnt += 1
                    max_drift = max(max_drift, rel)
            except ValueError:
                if peer_val.strip() == ref.cached_value.strip():
                    exact_cnt += 1
                else:
                    drift_cnt += 1

        if missing_sheets:
            res_status = "RESOLVED_SHEET_MISSING"
        elif drift_cnt > 0:
            res_status = "CONFIRMED_STALE_CACHE_DRIFT"
        else:
            res_status = "CONFIRMED_EXACT_MATCH"

        audits.append(
            ExternalLinkAuditRecord(
                workbook_name=wb_name,
                link_index=link_idx,
                raw_target=raw_target,
                link_health_tier=tier,
                syntactic_score=syn_score,
                active_formula_refs=active_counts[link_idx],
                resolution_status=res_status,
                resolved_local_path=str(matched_path),
                missing_sheets_count=len(missing_sheets),
                exact_match_cells=exact_cnt,
                drifted_cells=drift_cnt,
                max_rel_drift=round(max_drift, 6),
            )
        )

    return audits
