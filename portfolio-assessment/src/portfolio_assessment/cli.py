"""CLI entrypoint for scanning modeling workbooks and generating LES/MHS/MRI scorecards."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.scorer import assess_portfolio


def _default_workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    root = _default_workspace_root()
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
        default=[
            root / "brazil-power-v13" / "seed",
            root / "Eulr",
            root / "other models",
        ],
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
        default=root / "portfolio-assessment" / "reports",
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
