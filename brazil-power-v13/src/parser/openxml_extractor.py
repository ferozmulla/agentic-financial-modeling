"""Fast OpenXML (.xlsx / .xlsm) AST, Shared Formula, Named Range, and Button Binding Extractor."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

from defusedxml import ElementTree as ET

from src.cli.extract_baseline_fixtures import (
    NS,
    NS_REL,
    col_letter_to_index,
    index_to_col_letter,
    split_coord,
)
from src.parser.dag_builder import DependencyDAGBuilder
from src.parser.formula_normalizer import (
    a1_to_r1c1,
    canonicalize_a1_formula,
    compute_formula_hash,
    expand_shared_formula,
)
from src.parser.semantic_classifier import CellSemanticClassifier
from src.parser.technical_debt_scanner import TechnicalDebtScanner
from src.schemas.ast_dag import (
    CellSemanticRole,
    ExtractedCellRecord,
    ExtractedSheetRecord,
    ExtractedWorkbookGraph,
    MacroBindingRecord,
    NamedRangeRecord,
)

VML_MACRO_RE = re.compile(r"<x:FmlaMacro>([^<]+)</x:FmlaMacro>")
VML_ANCHOR_RE = re.compile(r"<x:Anchor>([^<]+)</x:Anchor>")


class OpenXMLExtractor:
    """Streams OpenXML (.xlsx / .xlsm) archives into a canonical ExtractedWorkbookGraph."""

    @classmethod
    def extract_from_path(
        cls,
        file_path: Path,
        spreadsheet_id: str = "local-seed-spreadsheet-id",
        workbook_name: str | None = None,
    ) -> ExtractedWorkbookGraph:
        """Extract complete AST and DAG from a local .xlsx or .xlsm file path."""
        raw_bytes = file_path.read_bytes()
        return cls.extract_from_bytes(
            raw_bytes=raw_bytes,
            spreadsheet_id=spreadsheet_id,
            workbook_name=workbook_name or file_path.name,
        )

    @classmethod
    def extract_from_bytes(
        cls,
        raw_bytes: bytes,
        spreadsheet_id: str = "local-seed-spreadsheet-id",
        workbook_name: str = "Regional Power Generation Techno-Economic Model",
    ) -> ExtractedWorkbookGraph:
        """Extract complete AST and DAG from in-memory .xlsx / .xlsm bytes."""
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
            # Security check: validate all ZIP member paths against path traversal
            for member in zf.namelist():
                if ".." in member or member.startswith("/"):
                    raise ValueError(f"Unsafe ZIP archive entry detected: {member}")

            # 1. Shared Strings
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                sst_xml = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in sst_xml.findall("main:si", NS):
                    shared_strings.append(
                        "".join(t.text or "" for t in si.findall(".//main:t", NS))
                    )

            # 2. Workbook sheets & relationships
            wb_xml = ET.fromstring(zf.read("xl/workbook.xml"))
            rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rid_to_target = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}

            sheet_elements = wb_xml.findall(".//main:sheet", NS)
            sheet_id_to_name: dict[int, str] = {}
            for idx, s_el in enumerate(sheet_elements):
                sheet_id_to_name[idx] = s_el.attrib["name"]

            # 3. Defined Names (Named Ranges)
            named_ranges: list[NamedRangeRecord] = []
            for dn in wb_xml.findall(".//main:definedName", NS):
                name_attr = dn.attrib.get("name", "")
                local_id_str = dn.attrib.get("localSheetId")
                local_id = int(local_id_str) if local_id_str is not None else None
                refers_to = (dn.text or "").strip()
                is_broken = "#REF!" in refers_to
                hidden = dn.attrib.get("hidden") in ("1", "true")
                named_ranges.append(
                    NamedRangeRecord(
                        name=name_attr,
                        local_sheet_id=local_id,
                        scope_sheet_name=sheet_id_to_name.get(local_id) if local_id is not None else None,
                        refers_to=refers_to,
                        is_broken_ref=is_broken,
                        hidden=hidden,
                    )
                )

            # 4. Parse all worksheets & expand shared formulas
            sheets_records: list[ExtractedSheetRecord] = []
            all_cells: list[ExtractedCellRecord] = []
            total_shared_cells = 0
            total_raw_f_tags = 0

            for s_idx, sheet_el in enumerate(sheet_elements, start=1):
                sname = sheet_el.attrib["name"]
                state = sheet_el.attrib.get("state", "visible")
                rid = sheet_el.attrib[f"{{{NS_REL}}}id"]
                target = rid_to_target[rid].lstrip("/")
                if not target.startswith("xl/"):
                    target = f"xl/{target}"

                s_xml = ET.fromstring(zf.read(target))
                c_elements = s_xml.findall(".//main:c", NS)

                # First pass: collect shared formula masters (si -> (master_formula, row, col))
                shared_masters: dict[int, tuple[str, int, int]] = {}
                for c_el in c_elements:
                    f_el = c_el.find("main:f", NS)
                    if f_el is not None and f_el.attrib.get("t") == "shared":
                        si_str = f_el.attrib.get("si")
                        if si_str is not None and f_el.text and f_el.text.strip():
                            c_str, r_num = split_coord(c_el.attrib["r"])
                            shared_masters[int(si_str)] = (
                                f_el.text.strip(),
                                r_num,
                                col_letter_to_index(c_str),
                            )

                sheet_populated = 0
                sheet_formulas = 0
                sheet_shared = 0

                for c_el in c_elements:
                    coord = c_el.attrib["r"]
                    c_str, r_num = split_coord(coord)
                    c_num = col_letter_to_index(c_str)
                    t_attr = c_el.attrib.get("t", "n")
                    f_el = c_el.find("main:f", NS)
                    v_el = c_el.find("main:v", NS)
                    is_el = c_el.find("main:is", NS)

                    raw_val_str: str | None = None
                    num_val: float | None = None

                    if v_el is not None and v_el.text is not None:
                        rv = v_el.text
                        if t_attr == "s":
                            idx = int(rv)
                            raw_val_str = (
                                shared_strings[idx] if 0 <= idx < len(shared_strings) else rv
                            )
                        elif t_attr in ("str", "e"):
                            raw_val_str = rv
                        elif t_attr == "b":
                            raw_val_str = "TRUE" if rv == "1" else "FALSE"
                        else:
                            raw_val_str = rv
                            try:
                                num_val = float(rv)
                            except ValueError:
                                num_val = None
                    elif is_el is not None:
                        raw_val_str = "".join(
                            t.text or "" for t in is_el.findall(".//main:t", NS)
                        )

                    raw_formula: str | None = None
                    canonical_formula: str | None = None
                    r1c1_formula: str | None = None
                    formula_hash: str | None = None
                    si_idx: int | None = None
                    is_master = False

                    if f_el is not None:
                        total_raw_f_tags += 1
                        f_type = f_el.attrib.get("t")
                        si_attr = f_el.attrib.get("si")
                        if f_type == "shared" and si_attr is not None:
                            si_idx = int(si_attr)
                            sheet_shared += 1
                            total_shared_cells += 1
                            if f_el.text and f_el.text.strip():
                                is_master = True
                                raw_formula = f_el.text.strip()
                                expanded = raw_formula
                            elif si_idx in shared_masters:
                                m_fml, m_r, m_c = shared_masters[si_idx]
                                raw_formula = m_fml
                                expanded = expand_shared_formula(m_fml, m_r, m_c, r_num, c_num)
                            else:
                                expanded = None
                        else:
                            raw_formula = (f_el.text or "").strip() or None
                            expanded = raw_formula

                        canonical_formula = canonicalize_a1_formula(expanded)
                        if canonical_formula:
                            sheet_formulas += 1
                            r1c1_formula = a1_to_r1c1(canonical_formula, r_num, c_num)
                            formula_hash = compute_formula_hash(r1c1_formula)

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
                            col_letter=c_str,
                            data_type=t_attr,
                            raw_value=raw_val_str,
                            numeric_value=num_val,
                            raw_formula=raw_formula,
                            canonical_formula=canonical_formula,
                            r1c1_formula=r1c1_formula,
                            formula_hash=formula_hash,
                            shared_group_index=si_idx,
                            is_shared_master=is_master,
                            semantic_role=role,
                        )
                    )

                sheets_records.append(
                    ExtractedSheetRecord(
                        sheet_index=s_idx,
                        sheet_name=sname,
                        visibility=state,
                        populated_cell_count=sheet_populated,
                        formula_cell_count=sheet_formulas,
                        shared_formula_count=sheet_shared,
                    )
                )

            # 5. Extract 31 interactive macro button bindings from xl/drawings/vmlDrawing1.vml
            macro_bindings: list[MacroBindingRecord] = []
            if "xl/drawings/vmlDrawing1.vml" in zf.namelist():
                vml_text = zf.read("xl/drawings/vmlDrawing1.vml").decode("utf-8", errors="replace")
                shape_blocks = vml_text.split("</v:shape>")
                for b_idx, block in enumerate(shape_blocks, start=1):
                    m_macro = VML_MACRO_RE.search(block)
                    if not m_macro:
                        continue
                    raw_ref = m_macro.group(1).strip()
                    macro_target = raw_ref.split("!")[-1].strip()
                    m_anchor = VML_ANCHOR_RE.search(block)
                    anchor_coord = f"B{40 + b_idx}"
                    if m_anchor:
                        parts = [p.strip() for p in m_anchor.group(1).split(",")]
                        if len(parts) >= 3 and parts[0].isdigit() and parts[2].isdigit():
                            col_1 = int(parts[0]) + 1
                            row_1 = int(parts[2]) + 1
                            anchor_coord = f"{index_to_col_letter(col_1)}{row_1}"
                    macro_bindings.append(
                        MacroBindingRecord(
                            sheet_name="General",
                            anchor_cell=anchor_coord,
                            button_label=macro_target,
                            macro_target=macro_target,
                            raw_macro_ref=raw_ref,
                        )
                    )

        # 6. Build Precedent -> Dependent DAG edges & scan technical debt
        dag_edges = DependencyDAGBuilder.build_edges(all_cells)
        debt_items = TechnicalDebtScanner.scan(named_ranges)
        broken_nr_count = sum(1 for nr in named_ranges if nr.is_broken_ref)
        role_counts = {role.value: 0 for role in CellSemanticRole}
        for c in all_cells:
            role_counts[c.semantic_role.value] += 1

        return ExtractedWorkbookGraph(
            workbook_name=workbook_name,
            spreadsheet_id=spreadsheet_id,
            sha256_hash=sha256_hash,
            sheets=sheets_records,
            cells=all_cells,
            dag_edges=dag_edges,
            named_ranges=named_ranges,
            macro_bindings=macro_bindings,
            technical_debt_items=debt_items,
            summary_metrics={
                "total_sheets": len(sheets_records),
                "total_populated_cells": len(all_cells),
                "total_raw_f_tags": total_raw_f_tags,
                "total_shared_formula_cells": total_shared_cells,
                "total_dag_edges": len(dag_edges),
                "total_named_ranges": len(named_ranges),
                "broken_named_ranges": broken_nr_count,
                "total_macro_bindings": len(macro_bindings),
                "role_counts": role_counts,
            },
        )
