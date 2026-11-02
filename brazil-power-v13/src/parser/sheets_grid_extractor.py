"""Parses native Google Sheets API spreadsheets.get(includeGridData=True) JSON into ExtractedWorkbookGraph."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.cli.extract_baseline_fixtures import index_to_col_letter
from src.parser.dag_builder import DependencyDAGBuilder
from src.parser.formula_normalizer import (
    a1_to_r1c1,
    canonicalize_a1_formula,
    compute_formula_hash,
)
from src.parser.semantic_classifier import CellSemanticClassifier
from src.schemas.ast_dag import (
    ExtractedCellRecord,
    ExtractedSheetRecord,
    ExtractedWorkbookGraph,
)


class SheetsGridExtractor:
    """Converts native Google Sheets API v4 GridData payloads into ExtractedWorkbookGraph."""

    @classmethod
    def extract_from_grid_json(
        cls,
        grid_payload: dict[str, Any],
    ) -> ExtractedWorkbookGraph:
        """Parse a Google Sheets spreadsheets.get(includeGridData=True) dictionary."""
        raw_json = json.dumps(grid_payload, sort_keys=True).encode("utf-8")
        sha256_hash = hashlib.sha256(raw_json).hexdigest()
        spreadsheet_id = str(grid_payload.get("spreadsheetId", "sheets-grid-id"))
        props = grid_payload.get("properties", {})
        workbook_name = str(props.get("title", "Regional Power Generation Techno-Economic Model"))

        sheets_records: list[ExtractedSheetRecord] = []
        all_cells: list[ExtractedCellRecord] = []

        for s_idx, sheet_obj in enumerate(grid_payload.get("sheets", []), start=1):
            s_props = sheet_obj.get("properties", {})
            sname = str(s_props.get("title", f"Sheet{s_idx}"))
            hidden = bool(s_props.get("hidden", False))
            visibility = "hidden" if hidden else "visible"

            sheet_populated = 0
            sheet_formulas = 0

            for grid_block in sheet_obj.get("data", []):
                start_row = int(grid_block.get("startRow", 0))
                start_col = int(grid_block.get("startColumn", 0))
                for r_offset, row_data in enumerate(grid_block.get("rowData", [])):
                    r_num = start_row + r_offset + 1
                    for c_offset, cell_data in enumerate(row_data.get("values", [])):
                        c_num = start_col + c_offset + 1
                        user_entered = cell_data.get("userEnteredValue", {})
                        effective = cell_data.get("effectiveValue", {})
                        if not user_entered and not effective:
                            continue

                        col_letter = index_to_col_letter(c_num)
                        coord = f"{col_letter}{r_num}"

                        raw_formula = user_entered.get("formulaValue")
                        canonical_formula = canonicalize_a1_formula(raw_formula)
                        r1c1_formula = a1_to_r1c1(canonical_formula, r_num, c_num)
                        formula_hash = compute_formula_hash(r1c1_formula)

                        num_val: float | None = None
                        raw_val: str | None = None
                        dtype = "n"

                        if "numberValue" in effective:
                            num_val = float(effective["numberValue"])
                            raw_val = str(num_val)
                        elif "stringValue" in effective:
                            raw_val = str(effective["stringValue"])
                            dtype = "s"
                        elif "boolValue" in effective:
                            raw_val = "TRUE" if effective["boolValue"] else "FALSE"
                            dtype = "b"

                        if canonical_formula:
                            sheet_formulas += 1

                        role = CellSemanticClassifier.classify(
                            sheet_name=sname,
                            cell_coord=coord,
                            row_num=r_num,
                            col_num=c_num,
                            canonical_formula=canonical_formula,
                            numeric_value=num_val,
                        )
                        sheet_populated += 1
                        all_cells.append(
                            ExtractedCellRecord(
                                sheet_name=sname,
                                cell_coord=coord,
                                row_num=r_num,
                                col_num=c_num,
                                col_letter=col_letter,
                                data_type=dtype,
                                raw_value=raw_val,
                                numeric_value=num_val,
                                raw_formula=raw_formula,
                                canonical_formula=canonical_formula,
                                r1c1_formula=r1c1_formula,
                                formula_hash=formula_hash,
                                semantic_role=role,
                            )
                        )

            sheets_records.append(
                ExtractedSheetRecord(
                    sheet_index=s_idx,
                    sheet_name=sname,
                    visibility=visibility,
                    populated_cell_count=sheet_populated,
                    formula_cell_count=sheet_formulas,
                )
            )

        dag_edges = DependencyDAGBuilder.build_edges(all_cells)
        return ExtractedWorkbookGraph(
            workbook_name=workbook_name,
            spreadsheet_id=spreadsheet_id,
            sha256_hash=sha256_hash,
            sheets=sheets_records,
            cells=all_cells,
            dag_edges=dag_edges,
            named_ranges=[],
            macro_bindings=[],
            technical_debt_items=[],
            summary_metrics={
                "total_sheets": len(sheets_records),
                "total_populated_cells": len(all_cells),
                "total_dag_edges": len(dag_edges),
            },
        )
