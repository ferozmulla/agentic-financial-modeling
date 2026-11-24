#!/usr/bin/env python3
"""Ingest seed workbook into BigQuery Digital Twin rows and setup BQML DDLs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from latinlr202409_bq_twin.config import settings
from latinlr202409_bq_twin.xlsx_compiler import compile_workbook_cached
from latinlr202409_bq_twin.schema_ddl import build_digital_twin_ddl, build_bqml_arima_ddl


def main() -> None:
    seed_path = os.environ.get(
        "ONBOARD_SEED_WORKBOOK_PATH",
        "/workspace/.agent/job/input/Latinlr202409_remediated.xlsx",
    )
    print(f"Resolving seed workbook from: {seed_path}")
    if not Path(seed_path).is_file():
        print(f"Error: Seed workbook not found at {seed_path}")
        sys.exit(1)

    print("Compiling workbook to memory row-dicts (fast XML iterparse)...")
    compiled = compile_workbook_cached(
        seed_path,
        workbook_id=settings.workbook_id,
        version_id=settings.base_version_id,
        include_row_dicts=True,
    )
    print(f"Successfully compiled {len(compiled.sheet_names)} sheets and {len(compiled.cell_rows)} cell rows.")

    print("\nGenerating BigQuery Digital Twin and ARIMA_PLUS DDLs:")
    ddls = build_digital_twin_ddl(settings.project_id, settings.dataset_id)
    arima_ddls = build_bqml_arima_ddl(settings.project_id, settings.dataset_id)

    for idx, ddl in enumerate(ddls + arima_ddls, 1):
        # Clean print first 100 characters of each DDL statement
        cleaned = " ".join(ddl.strip().split())
        print(f"  DDL {idx:02d}: {cleaned[:100]}...")

    print("\nTo load to BigQuery, ensure GOOGLE_APPLICATION_CREDENTIALS is set.")
    print("Staging completed successfully (Dry-Run).")


if __name__ == "__main__":
    main()
