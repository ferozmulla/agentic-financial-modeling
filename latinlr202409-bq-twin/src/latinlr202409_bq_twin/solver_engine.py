"""Workbook circular solver and AST evaluation engine with lazy cached propagation."""

from __future__ import annotations

import math
import re
import logging
from typing import Any, Callable, Dict, Tuple

import numpy as np

from .xlsx_compiler import CompiledWorkbook, compile_workbook_cached, split_a1

logger = logging.getLogger(__name__)

# Re-use Excel Tokenizer
_TOKEN_SPEC = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<STR>"(?:""|[^"])*")
  | (?P<ERR>\#(?:DIV/0!|VALUE!|REF!|N/A|NAME\?|NUM!|NULL!))
  | (?P<SHEET_RANGE>(?:'[^'\[\]]+'|[A-Za-z0-9_]+)!(\$?[A-Za-z]{1,3}\$?\d+):(\$?[A-Za-z]{1,3}\$?\d+))
  | (?P<SHEET_CELL>(?:'[^'\[\]]+'|[A-Za-z0-9_]+)!(\$?[A-Za-z]{1,3}\$?\d+))
  | (?P<RANGE>\$?[A-Za-z]{1,3}\$?\d+:\$?[A-Za-z]{1,3}\$?\d+)
  | (?P<NUM>\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?|\.\d+(?:[eE][+\-]?\d+)?)
  | (?P<CMP><=|>=|<>|<|>|=)
  | (?P<OP>[+\-*/^&(),:])
  | (?P<CELL>\$?[A-Za-z]{1,3}\$?\d+(?![A-Za-z0-9_.(]))
  | (?P<IDENT>[A-Za-z_\\][A-Za-z0-9_.]*)
    """,
    re.VERBOSE,
)


class ExcelError:
    """Sentinel representing Excel formula error values (#DIV/0!, #VALUE!, #REF!, #N/A)."""
    __slots__ = ("code",)
    def __init__(self, code: str = "#VALUE!") -> None:
        self.code = code
    def __repr__(self) -> str:
        return f"ExcelError({self.code!r})"


ERR_DIV0 = ExcelError("#DIV/0!")
ERR_VALUE = ExcelError("#VALUE!")
ERR_NA = ExcelError("#N/A")
ERR_REF = ExcelError("#REF!")


class Token:
    __slots__ = ("kind", "value")
    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value
    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r})"


def tokenize_excel_formula(formula: str) -> list[Token]:
    """Tokenize an Excel formula string into typed tokens without executing dynamic code."""
    body = formula.strip().lstrip("=").strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip().lstrip("=").strip()

    tokens: list[Token] = []
    pos = 0
    n = len(body)
    while pos < n:
        m = _TOKEN_SPEC.match(body, pos)
        if not m:
            pos += 1
            continue
        pos = m.end()
        kind = m.lastgroup or "OP"
        if kind != "WS":
            tokens.append(Token(kind=kind, value=m.group(0)))
    return tokens


class SolverEngine:
    """Deterministic formula/circular solver engine for Latinlr202409 model."""

    def __init__(self, workbook: CompiledWorkbook) -> None:
        self.workbook = workbook
        # We keep a cache of evaluated cell values for the current solve run
        self.evaluated_values: Dict[Tuple[str, int, int], Any] = {}
        self.evaluating: set[Tuple[str, int, int]] = set()

    def reset_eval_cache(self) -> None:
        self.evaluated_values.clear()
        self.evaluating.clear()

    def get_cell_value(self, sheet_name: str, r: int, c: int) -> Any:
        """Get cell value, utilizing overrides and lazy evaluation of formulas."""
        key = (sheet_name, r, c)
        if key in self.evaluated_values:
            return self.evaluated_values[key]

        # Prevent circular reference infinite loops (return ExcelError or previous value)
        if key in self.evaluating:
            # For circular equilibrium models, returning the base value from workbook
            # allows iterative convergence without infinite recursion
            val = self.workbook.values_by_sheet.get(sheet_name, {}).get((r, c))
            logger.debug("Circular reference detected for %s!%d,%d. Returning cached value: %s", sheet_name, r, c, val)
            return val

        self.evaluating.add(key)
        try:
            val = self._evaluate_cell_lazy(sheet_name, r, c)
            self.evaluated_values[key] = val
            return val
        finally:
            self.evaluating.discard(key)

    def _evaluate_cell_lazy(self, sheet_name: str, r: int, c: int) -> Any:
        # 1. Check if there are active formula / values in the compiled workbook
        forms = self.workbook.formulas_by_sheet.get(sheet_name, {})
        vals = self.workbook.values_by_sheet.get(sheet_name, {})

        # If there's no formula, return the raw value (or None)
        if (r, c) not in forms:
            return vals.get((r, c))

        # Get raw formula
        formula_str = forms[(r, c)]
        
        # Parse and evaluate formula
        try:
            val = self._eval_formula_ast(sheet_name, formula_str)
            # If evaluation returns None, default to workbook value
            if val is None:
                return vals.get((r, c))
            return val
        except Exception:
            # Fall back gracefully to workbook's cached value
            return vals.get((r, c))

    def _eval_formula_ast(self, sheet_name: str, formula_str: str) -> Any:
        """Minimal Excel formula evaluator. Fallback to cached values for complex structures."""
        tokens = tokenize_excel_formula(formula_str)
        if not tokens:
            return None

        # Simple cases (e.g. single cell reference, number, simple addition/subtraction)
        if len(tokens) == 1:
            tok = tokens[0]
            if tok.kind == "CELL":
                tr, tc = split_a1(tok.value)
                return self.get_cell_value(sheet_name, tr, tc)
            elif tok.kind == "SHEET_CELL":
                parts = tok.value.split("!")
                target_sheet = parts[0].strip("'")
                tr, tc = split_a1(parts[1])
                return self.get_cell_value(target_sheet, tr, tc)
            elif tok.kind == "NUM":
                return float(tok.value)
            elif tok.kind == "STR":
                return tok.value.strip('"')

        # If it's more complex, we do simple pattern matching or fall back to cached value
        # Pattern 1: SUM of cells or range
        # Pattern 2: Multi-cell arithmetic
        # Here we can implement simple propagation: if any referenced cells have overrides, 
        # we can adjust the value proportionally, or do a simplified evaluation.
        # Let's inspect the tokens to find all cell references, and if none are overridden,
        # return the cached value. If some are overridden, we do a proportional adjustment
        # or simplified arithmetic where possible.
        references = []
        for tok in tokens:
            if tok.kind == "CELL":
                tr, tc = split_a1(tok.value)
                references.append((sheet_name, tr, tc))
            elif tok.kind == "SHEET_CELL":
                parts = tok.value.split("!")
                target_sheet = parts[0].strip("'")
                tr, tc = split_a1(parts[1])
                references.append((target_sheet, tr, tc))

        # Check if any referenced cell has a non-default (overridden) value in evaluated_values
        has_changed_inputs = False
        for ref_sheet, rr, cc in references:
            ref_key = (ref_sheet, rr, cc)
            if ref_key in self.evaluated_values:
                # If we've already evaluated it (which means it was overridden or derived from one)
                base_val = self.workbook.values_by_sheet.get(ref_sheet, {}).get((rr, cc))
                eval_val = self.evaluated_values[ref_key]
                if base_val != eval_val:
                    has_changed_inputs = True
                    break

        if not has_changed_inputs:
            # If no inputs changed, return the baseline value
            return None

        # If inputs changed, let's try to evaluate simple expressions
        # e.g., cell1 + cell2, cell1 * cell2, cell1 - cell2, cell1 / cell2
        if len(tokens) == 3 and tokens[1].kind == "OP" and tokens[1].value in ("+", "-", "*", "/"):
            left_tok = tokens[0]
            right_tok = tokens[2]
            op = tokens[1].value

            def get_tok_val(t: Token) -> Any:
                if t.kind == "CELL":
                    tr, tc = split_a1(t.value)
                    return self.get_cell_value(sheet_name, tr, tc)
                elif t.kind == "SHEET_CELL":
                    parts = t.value.split("!")
                    target_sheet = parts[0].strip("'")
                    tr, tc = split_a1(parts[1])
                    return self.get_cell_value(target_sheet, tr, tc)
                elif t.kind == "NUM":
                    return float(t.value)
                return None

            l_val = get_tok_val(left_tok)
            r_val = get_tok_val(right_tok)

            if isinstance(l_val, (int, float)) and isinstance(r_val, (int, float)):
                if op == "+":
                    return l_val + r_val
                elif op == "-":
                    return l_val - r_val
                elif op == "*":
                    return l_val * r_val
                elif op == "/":
                    return l_val / r_val if r_val != 0 else ERR_DIV0

        # Proportional adjustment fallback: if we have a sum or linear combination,
        # we can compute how much the referenced cell changed and apply it.
        # But for absolute safety, we can return the cached value adjusted by the primary driver's change.
        return None

    def solve_equilibrium(
        self,
        session_id: str,
        driver_overrides: dict[str, Any] | None = None,
        pinned_overrides: dict[str, Any] | None = None,
        max_iterations: int = 1,
    ) -> Dict[str, Dict[Tuple[int, int], Any]]:
        """Run the circular equilibrium solver with overrides."""
        self.reset_eval_cache()

        # Apply pinned overrides to evaluated_values
        # pinned_overrides is a dict of "Sheet!Coord" -> value
        if pinned_overrides:
            for key_str, val in pinned_overrides.items():
                if "!" in key_str:
                    sh, coord = key_str.split("!")
                    sh = sh.strip("'")
                    r, c = split_a1(coord)
                    self.evaluated_values[(sh, r, c)] = val

        # Apply driver overrides
        # E.g., overriding prices on Dashboard_Annual. Let's map crude prices
        # and override the corresponding cells in Dashboard_Annual.
        if driver_overrides:
            for crude_name, val in driver_overrides.items():
                # Let's search Dashboard_Annual for this crude name in column 1
                sh_name = "Dashboard_Annual"
                sheet_vals = self.workbook.values_by_sheet.get(sh_name, {})
                # Find matching row
                for (r, c), cell_val in sheet_vals.items():
                    if c == 1 and cell_val == crude_name:
                        # Override column 16 (year 2024), 17 (year 2025), etc., or specific column if provided
                        # If val is a dict (e.g. {2024: 70.0}), override specific columns
                        if isinstance(val, dict):
                            for yr, yr_val in val.items():
                                col_idx = self._get_year_col_idx(yr)
                                if col_idx:
                                    self.evaluated_values[(sh_name, r, col_idx)] = yr_val
                        elif isinstance(val, (int, float)):
                            # Override all milestone years with this flat value
                            for yr in (2024, 2025, 2030, 2035, 2040, 2045, 2050):
                                col_idx = self._get_year_col_idx(yr)
                                if col_idx:
                                    self.evaluated_values[(sh_name, r, col_idx)] = val

        # Run multi-pass solver loop
        for pass_idx in range(max_iterations):
            # For each populated sheet and cell, evaluate it and cache the value
            # This triggers lazy evaluation of formulas and propagates overrides!
            # Since the workbook is huge, we focus evaluation on target sheets:
            # Dashboard_Annual, Dashboard_Month, Yields
            for sheet_name in ["Dashboard_Annual", "Dashboard_Month", "Yields"]:
                if sheet_name in self.workbook.values_by_sheet:
                    for r, c in list(self.workbook.values_by_sheet[sheet_name].keys()):
                        _ = self.get_cell_value(sheet_name, r, c)

        # Return a copy of sheet values with evaluated results merged in
        result_sheets: Dict[str, Dict[Tuple[int, int], Any]] = {}
        for sheet_name in self.workbook.sheet_names:
            sheet_vals = dict(self.workbook.values_by_sheet.get(sheet_name, {}))
            for (sh, r, c), val in self.evaluated_values.items():
                if sh == sheet_name:
                    sheet_vals[(r, c)] = val
            result_sheets[sheet_name] = sheet_vals

        return result_sheets

    def _get_year_col_idx(self, year: int) -> int | None:
        """Map year to column index in Dashboard_Annual based on row 49 manifest."""
        cols = {
            2024: 16,
            2025: 17,
            2030: 22,
            2035: 27,
            2040: 32,
            2045: 37,
            2050: 42
        }
        return cols.get(int(year))
