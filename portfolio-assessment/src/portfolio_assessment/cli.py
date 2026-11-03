"""CLI entrypoint for scanning modeling workbooks and generating LES/MHS/MRI scorecards."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.scorer import assess_portfolio


def _package_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_scan_dirs() -> list[Path]:
    pkg_root = _package_project_root()
    platform_root = pkg_root.parent
    monorepo_dirs = [
        platform_root / "brazil-power-v13" / "seed",
        platform_root / "Eulr",
        platform_root / "other models",
    ]
    existing = [d for d in monorepo_dirs if d.exists()]
    if existing:
        return existing
    workbooks_dir = pkg_root / "workbooks"
    return [workbooks_dir] if workbooks_dir.exists() else [pkg_root]


def build_parser() -> argparse.ArgumentParser:
    pkg_root = _package_project_root()
    parser = argparse.ArgumentParser(
        prog="assess-portfolio",
        description=(
            "Compute Logic Extractability (LES), Model Hygiene (MHS), "
            "and Modernization Readiness (MRI)."
        ),
    )
    parser.add_argument(
        "--scan-dirs",
        nargs="+",
        type=Path,
        default=_default_scan_dirs(),
        help="Directories or .xlsx/.xlsm files to scan (read-only).",
    )
    parser.add_argument(
        "--reference-roots",
        nargs="*",
        type=Path,
        default=[],
        help="Optional local/synced SharePoint/OneDrive folders to confirm external links & drift.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=pkg_root / "reports",
        help="Output directory for Markdown and CSV scorecards.",
    )
    parser.add_argument(
        "--include-all-vintages",
        action="store_true",
        help="Score superseded vintage archive files (e.g. Callr202406 alongside Callr202409).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scorecards = assess_portfolio(
        scan_dirs=args.scan_dirs,
        output_dir=args.output_dir,
        reference_roots=args.reference_roots,
        include_all_vintages=args.include_all_vintages,
    )
    print(f"Evaluated {len(scorecards)} workbooks -> reports written to {args.output_dir}")
    for sc in scorecards:
        print(
            f"  {sc.workbook_name:48s} | LES={sc.les.score:5.1f}% | "
            f"MHS={sc.mhs.score:5.1f}% (Defect={sc.defect_rate:4.1f}%) | "
            f"MRI={sc.mri:5.1f}% | {sc.readiness_tier}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
