"""Cell-Level Precedent -> Dependent Directed Acyclic Graph (DAG) Builder (FR-B03)."""

from __future__ import annotations

import re
from collections import deque

from src.cli.extract_baseline_fixtures import expand_range_coords
from src.schemas.ast_dag import DependencyEdgeRecord, ExtractedCellRecord

# Matches optional sheet name ('LT Capex'! or General!) + A1 cell or A1:B2 range
REF_PATTERN = re.compile(
    r"(?:(?:'([^']+)'|([A-Za-z0-9_]+))!)?(\$?[A-Z]{1,3}\$?\d+)(?::(\$?[A-Z]{1,3}\$?\d+))?"
)


class DependencyDAGBuilder:
    """Extracts Precedent -> Dependent cell dependency edges across all 22 sheets."""

    @staticmethod
    def build_edges(cells: list[ExtractedCellRecord]) -> list[DependencyEdgeRecord]:
        """Parse all formula cells into Precedent -> Dependent edges."""
        edges: list[DependencyEdgeRecord] = []
        for cell in cells:
            fml = cell.canonical_formula
            if not fml:
                continue
            seen_precedents: set[tuple[str, str]] = set()
            for m in REF_PATTERN.finditer(fml):
                quoted_sheet, bare_sheet, start_ref, end_ref = (
                    m.group(1),
                    m.group(2),
                    m.group(3),
                    m.group(4),
                )
                prec_sheet = quoted_sheet or bare_sheet or cell.sheet_name
                clean_start = start_ref.replace("$", "")
                if end_ref:
                    clean_end = end_ref.replace("$", "")
                    rng_coords = expand_range_coords(f"{clean_start}:{clean_end}")
                    # Cap huge range expansions if any, but 45-col IRR(B63:AT63) is 45 coords
                    for rc in rng_coords[:120]:
                        key = (prec_sheet, rc)
                        if key not in seen_precedents:
                            seen_precedents.add(key)
                            edges.append(
                                DependencyEdgeRecord(
                                    precedent_sheet=prec_sheet,
                                    precedent_coord=rc,
                                    dependent_sheet=cell.sheet_name,
                                    dependent_coord=cell.cell_coord,
                                    reference_type="RANGE_EXPANSION",
                                )
                            )
                else:
                    key = (prec_sheet, clean_start)
                    if key not in seen_precedents:
                        seen_precedents.add(key)
                        edges.append(
                            DependencyEdgeRecord(
                                precedent_sheet=prec_sheet,
                                precedent_coord=clean_start,
                                dependent_sheet=cell.sheet_name,
                                dependent_coord=cell.cell_coord,
                                reference_type="DIRECT_CELL",
                            )
                        )
        return edges

    @staticmethod
    def trace_downstream_dependents(
        edges: list[DependencyEdgeRecord],
        sheet_name: str,
        cell_coord: str,
        max_depth: int = 8,
    ) -> list[dict[str, str | int]]:
        """Breadth-first traversal finding all downstream dependent cells (blast radius)."""
        adj: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for e in edges:
            adj.setdefault((e.precedent_sheet, e.precedent_coord), []).append(
                (e.dependent_sheet, e.dependent_coord)
            )

        visited: set[tuple[str, str]] = {(sheet_name, cell_coord)}
        queue: deque[tuple[str, str, int]] = deque([(sheet_name, cell_coord, 0)])
        results: list[dict[str, str | int]] = []

        while queue:
            curr_s, curr_c, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for nxt_s, nxt_c in adj.get((curr_s, curr_c), []):
                if (nxt_s, nxt_c) not in visited:
                    visited.add((nxt_s, nxt_c))
                    results.append(
                        {
                            "sheet_name": nxt_s,
                            "cell_coord": nxt_c,
                            "hop_distance": depth + 1,
                        }
                    )
                    queue.append((nxt_s, nxt_c, depth + 1))
        return results
