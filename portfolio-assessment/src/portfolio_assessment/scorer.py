"""Portfolio discovery, vintage deduplication, and end-to-end workbook assessment."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.extractability import compute_extractability_pillar
from portfolio_assessment.hygiene import compute_hygiene_pillar
from portfolio_assessment.models import (
    CellDefectRecord,
    ExternalLinkAuditRecord,
    WorkbookScorecard,
)
from portfolio_assessment.reference_resolver import PeerLookup, resolve_workbook_external_links
from portfolio_assessment.reporter import write_portfolio_reports
from portfolio_assessment.weights import classify_archetype, compute_mri_and_tier
from portfolio_assessment.xml_inspector import scan_workbook_openxml

_FAMILY_KEY_RE = re.compile(r"(20\d{4}).*$", re.IGNORECASE)


def _family_and_rank(path: Path) -> tuple[str, tuple[str, int]]:
    stem = path.stem
    m = _FAMILY_KEY_RE.search(stem)
    if not m:
        return (stem.lower(), ("999999", 1))
    family = stem[: m.start()].strip(" _-").lower()
    if not family:
        return (stem.lower(), ("999999", 1))
    vintage = m.group(1)
    is_canonical = 1 if stem.lower() == f"{family}{vintage}" else 0
    return (family, (vintage, is_canonical))


def discover_workbooks(
    scan_dirs: Sequence[Path],
    include_all_vintages: bool = False,
) -> list[Path]:
    """Find all .xlsx and .xlsm files across scan_dirs, optionally deduplicating older vintages."""
    found: dict[Path, Path] = {}
    for d in scan_dirs:
        if not d.exists():
            continue
        if d.is_file() and d.suffix.lower() in (".xlsx", ".xlsm") and not d.name.startswith("~$"):
            found[d.resolve()] = d
        elif d.is_dir():
            for p in sorted(d.rglob("*")):
                if (
                    p.is_file()
                    and p.suffix.lower() in (".xlsx", ".xlsm")
                    and not p.name.startswith("~$")
                    and not {".venv", "tests", "reports"}.intersection(p.parts)
                ):
                    found[p.resolve()] = p

    candidates = sorted(found.values(), key=lambda x: x.name.lower())
    if include_all_vintages:
        return candidates

    best_by_family: dict[str, tuple[tuple[str, int], Path]] = {}
    for p in candidates:
        fam, rank_key = _family_and_rank(p)
        prev = best_by_family.get(fam)
        if prev is None or rank_key > prev[0]:
            best_by_family[fam] = (rank_key, p)

    return sorted((v[1] for v in best_by_family.values()), key=lambda x: x.name.lower())


def assess_workbook(
    xlsx_path: Path,
    reference_roots: Sequence[Path] = (),
    peer_cache: dict[Path, PeerLookup] | None = None,
) -> tuple[WorkbookScorecard, list[CellDefectRecord], list[ExternalLinkAuditRecord]]:
    """Run full read-only OpenXML + VBA + reference assessment on a single workbook."""
    scan = scan_workbook_openxml(xlsx_path)
    if peer_cache is not None and xlsx_path.resolve() not in peer_cache:
        lookup: dict[tuple[str, str], str | None] = {}
        for ps_name, ps_summary in scan.sheets.items():
            for row_cells in ps_summary.cells_by_row.values():
                for c in row_cells:
                    lookup[(ps_name, c.coord)] = c.value
        peer_cache[xlsx_path.resolve()] = (set(scan.sheets.keys()), lookup)

    link_audits = resolve_workbook_external_links(
        scan, reference_roots=reference_roots, peer_cache=peer_cache
    )
    les, e_stats = compute_extractability_pillar(scan)
    mhs, defects, h_stats = compute_hygiene_pillar(scan, link_audits)

    defect_rate = round(100.0 - mhs.score, 2)
    mri, tier, action = compute_mri_and_tier(les.score, mhs.score)
    archetype = classify_archetype(
        total_formula_cells=scan.total_formula_cells,
        xll_udf_cells=e_stats["xll_udf_cells"],
        has_vba=scan.vba.has_executable_vba,
        is_iterative=scan.calc_pr.get("iterate") == "1",
        has_time_axis=scan.has_time_axis,
    )

    scorecard = WorkbookScorecard(
        workbook_name=xlsx_path.name,
        workbook_path=str(xlsx_path),
        file_size_mb=scan.file_size_mb,
        archetype=archetype,
        vintage_tag=scan.vintage_tag or "N/A",
        sheet_count=len(scan.sheet_names),
        total_populated_cells=scan.total_populated_cells,
        total_formula_cells=scan.total_formula_cells,
        les=les,
        mhs=mhs,
        defect_rate=defect_rate,
        mri=mri,
        readiness_tier=tier,
        recommended_action=action,
        telemetry={
            **e_stats,
            **h_stats,
            "external_links_declared": len(scan.declared_external_links),
        },
    )
    return scorecard, defects, link_audits


def assess_portfolio(
    scan_dirs: Sequence[Path],
    output_dir: Path,
    reference_roots: Sequence[Path] = (),
    include_all_vintages: bool = False,
) -> list[WorkbookScorecard]:
    """Assess all discovered workbooks, sort by MRI descending, and emit Markdown + CSV reports."""
    workbooks = discover_workbooks(scan_dirs, include_all_vintages=include_all_vintages)
    scorecards: list[WorkbookScorecard] = []
    all_defects: list[CellDefectRecord] = []
    all_links: list[ExternalLinkAuditRecord] = []
    shared_peer_cache: dict[Path, PeerLookup] = {}

    for wb_path in workbooks:
        sc, defs, lnks = assess_workbook(
            wb_path, reference_roots=reference_roots, peer_cache=shared_peer_cache
        )
        scorecards.append(sc)
        all_defects.extend(defs)
        all_links.extend(lnks)

    scorecards.sort(key=lambda s: (-s.mri, s.workbook_name.lower()))
    write_portfolio_reports(output_dir, scorecards, all_defects, all_links)
    return scorecards
