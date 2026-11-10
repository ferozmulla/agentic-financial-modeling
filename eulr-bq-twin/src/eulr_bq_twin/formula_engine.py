"""Deterministic 26-function Excel Formula AST compiler & dependency-cone evaluator (zero `eval()`)."""

from __future__ import annotations

import datetime as dt
import math
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from eulr_bq_twin.models import (
    EulrBaselineSnapshot,
    UpstreamMode,
    col_letter_to_index,
    split_a1_coord,
)

# Error sentinel object for #DIV/0!, #REF!, #VALUE!, #N/A
class ExcelError:
    __slots__ = ("code",)

    def __init__(self, code: str = "#VALUE!") -> None:
        self.code = code

    def __repr__(self) -> str:
        return f"ExcelError({self.code!r})"


ERR_DIV0 = ExcelError("#DIV/0!")
ERR_VALUE = ExcelError("#VALUE!")
ERR_NA = ExcelError("#N/A")
ERR_REF = ExcelError("#REF!")

_TOKEN_SPEC = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<STR>"(?:""|[^"])*")
  | (?P<ERR>\#(?:DIV/0!|VALUE!|REF!|N/A|NAME\?|NUM!|NULL!))
  | (?P<EXT_CELL>\[(\d+)\](?:'[^']+'|[A-Za-z0-9_.\s]+)!\$?[A-Za-z]{1,3}\$?\d+)
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

_CELL_ONLY_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def tokenize_excel_formula(formula: str) -> list[Token]:
    body = formula.strip()
    if body.startswith("="):
        body = body[1:].strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip()
        if body.startswith("="):
            body = body[1:].strip()

    tokens: list[Token] = []
    pos = 0
    n = len(body)
    while pos < n:
        m = _TOKEN_SPEC.match(body, pos)
        if not m:
            # Skip unexpected character safely
            pos += 1
            continue
        kind = m.lastgroup or "UNK"
        val = m.group()
        pos = m.end()
        if kind == "WS":
            continue
        tokens.append(Token(kind, val))
    return tokens


# Compact tuple AST node tags:
# ("NUM", float)
# ("STR", str)
# ("BOOL", bool)
# ("ERR", ExcelError)
# ("CELL", sheet_name, row_num, col_num)
# ("RANGE", sheet_name, r1, c1, r2, c2)
# ("EXT_SELF",)  -> resolves via current cell's dt_external_links or cached fallback
# ("UNARY", op, child)
# ("BIN", op, left, right)
# ("CALL", func_upper, list[ast])


class _FormulaParser:
    def __init__(
        self,
        tokens: list[Token],
        current_sheet: str,
        named_map: dict[tuple[str | None, str], tuple[str, int, int, int, int]],
    ) -> None:
        self.tokens = tokens
        self.pos = 0
        self.current_sheet = current_sheet
        self.named_map = named_map
        self.deps: set[tuple[str, int, int]] = set()
        self.has_offset_or_ext = False

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> tuple[Any, ...]:
        if not self.tokens:
            return ("NUM", 0.0)
        node = self._parse_comparison()
        return node

    def _parse_comparison(self) -> tuple[Any, ...]:
        left = self._parse_concat()
        while (tok := self.peek()) is not None and tok.kind == "CMP":
            op = self.consume().value
            right = self._parse_concat()
            left = ("BIN", op, left, right)
        return left

    def _parse_concat(self) -> tuple[Any, ...]:
        left = self._parse_additive()
        while (tok := self.peek()) is not None and tok.kind == "OP" and tok.value == "&":
            self.consume()
            right = self._parse_additive()
            left = ("BIN", "&", left, right)
        return left

    def _parse_additive(self) -> tuple[Any, ...]:
        left = self._parse_multiplicative()
        while (tok := self.peek()) is not None and tok.kind == "OP" and tok.value in ("+", "-"):
            op = self.consume().value
            right = self._parse_multiplicative()
            left = ("BIN", op, left, right)
        return left

    def _parse_multiplicative(self) -> tuple[Any, ...]:
        left = self._parse_power()
        while (tok := self.peek()) is not None and tok.kind == "OP" and tok.value in ("*", "/"):
            op = self.consume().value
            right = self._parse_power()
            left = ("BIN", op, left, right)
        return left

    def _parse_power(self) -> tuple[Any, ...]:
        left = self._parse_unary()
        while (tok := self.peek()) is not None and tok.kind == "OP" and tok.value == "^":
            self.consume()
            right = self._parse_unary()
            left = ("BIN", "^", left, right)
        return left

    def _parse_unary(self) -> tuple[Any, ...]:
        tok = self.peek()
        if tok is not None and tok.kind == "OP" and tok.value in ("+", "-"):
            op = self.consume().value
            child = self._parse_unary()
            return child if op == "+" else ("UNARY", "-", child)
        return self._parse_primary()

    def _record_range_deps(self, sname: str, r1: int, c1: int, r2: int, c2: int) -> None:
        r_lo, r_hi = min(r1, r2), max(r1, r2)
        c_lo, c_hi = min(c1, c2), max(c1, c2)
        # Bound dependency tracking for huge whole-sheet ranges
        if (r_hi - r_lo + 1) * (c_hi - c_lo + 1) <= 2500:
            for rr in range(r_lo, r_hi + 1):
                for cc in range(c_lo, c_hi + 1):
                    self.deps.add((sname, rr, cc))

    def _parse_primary(self) -> tuple[Any, ...]:
        tok = self.peek()
        if tok is None:
            return ("NUM", 0.0)

        if tok.kind == "OP" and tok.value == "(":
            self.consume()
            inner = self._parse_comparison()
            if (nxt := self.peek()) is not None and nxt.kind == "OP" and nxt.value == ")":
                self.consume()
            return inner

        if tok.kind == "NUM":
            self.consume()
            return ("NUM", float(tok.value))

        if tok.kind == "STR":
            self.consume()
            return ("STR", tok.value[1:-1].replace('""', '"'))

        if tok.kind == "ERR":
            self.consume()
            return ("ERR", ExcelError(tok.value))

        if tok.kind == "EXT_CELL":
            self.consume()
            self.has_offset_or_ext = True
            return ("EXT_SELF",)

        if tok.kind == "SHEET_RANGE":
            raw = self.consume().value
            sh_part, rng_part = raw.split("!", 1)
            sname = sh_part.strip("'")
            p1, p2 = rng_part.split(":", 1)
            r1, c1 = split_a1_coord(p1)
            r2, c2 = split_a1_coord(p2)
            self._record_range_deps(sname, r1, c1, r2, c2)
            return ("RANGE", sname, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))

        if tok.kind == "SHEET_CELL":
            raw = self.consume().value
            sh_part, c_part = raw.split("!", 1)
            sname = sh_part.strip("'")
            r1, c1 = split_a1_coord(c_part)
            self.deps.add((sname, r1, c1))
            return ("CELL", sname, r1, c1)

        if tok.kind == "RANGE":
            raw = self.consume().value
            p1, p2 = raw.split(":", 1)
            r1, c1 = split_a1_coord(p1)
            r2, c2 = split_a1_coord(p2)
            self._record_range_deps(self.current_sheet, r1, c1, r2, c2)
            return ("RANGE", self.current_sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))

        if tok.kind == "CELL":
            raw = self.consume().value
            r1, c1 = split_a1_coord(raw)
            if c1 <= 512:
                self.deps.add((self.current_sheet, r1, c1))
                return ("CELL", self.current_sheet, r1, c1)
            return ("ERR", ERR_NA)

        if tok.kind == "IDENT":
            ident = self.consume().value
            upper_id = ident.upper()
            nxt = self.peek()
            if nxt is not None and nxt.kind == "OP" and nxt.value == "(":
                self.consume()  # '('
                args: list[tuple[Any, ...]] = []
                if not ((p := self.peek()) is not None and p.kind == "OP" and p.value == ")"):
                    while True:
                        if (p := self.peek()) is not None and p.kind == "OP" and p.value in (",", ")"):
                            args.append(("NUM", 0.0))
                        else:
                            args.append(self._parse_comparison())
                        p2 = self.peek()
                        if p2 is not None and p2.kind == "OP" and p2.value == ",":
                            self.consume()
                            continue
                        break
                if (p3 := self.peek()) is not None and p3.kind == "OP" and p3.value == ")":
                    self.consume()
                if upper_id == "OFFSET":
                    self.has_offset_or_ext = True
                return ("CALL", upper_id, args)

            if upper_id == "TRUE":
                return ("BOOL", True)
            if upper_id == "FALSE":
                return ("BOOL", False)

            m_cell = _CELL_ONLY_RE.match(ident)
            if m_cell:
                c_idx = col_letter_to_index(m_cell.group(1))
                r_idx = int(m_cell.group(2))
                if c_idx <= 512:
                    self.deps.add((self.current_sheet, r_idx, c_idx))
                    return ("CELL", self.current_sheet, r_idx, c_idx)

            # Named range lookup (sheet-scoped first, then workbook-scoped)
            nm_target = self.named_map.get((self.current_sheet, upper_id)) or self.named_map.get(
                (None, upper_id)
            )
            if nm_target is not None:
                sname, r1, c1, r2, c2 = nm_target
                if r1 == r2 and c1 == c2:
                    self.deps.add((sname, r1, c1))
                    return ("CELL", sname, r1, c1)
                self._record_range_deps(sname, r1, c1, r2, c2)
                return ("RANGE", sname, r1, c1, r2, c2)

            return ("ERR", ERR_NA)

        self.consume()
        return ("NUM", 0.0)


def _to_float(val: Any) -> float | ExcelError:
    if isinstance(val, ExcelError):
        return val
    if val is None or val == "":
        return 0.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return ERR_DIV0
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return 0.0
        if s.startswith("#"):
            return ExcelError(s)
        try:
            return float(s)
        except ValueError:
            return ERR_VALUE
    return ERR_VALUE


def _to_bool(val: Any) -> bool | ExcelError:
    if isinstance(val, ExcelError):
        return val
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0.0 and not math.isnan(val)
    if isinstance(val, str):
        u = val.strip().upper()
        if u == "TRUE":
            return True
        if u == "FALSE":
            return False
    return False


def _excel_eq(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    if (a is None or a == 0 or a == "") and (b is None or b == 0 or b == ""):
        if type(a) is str and type(b) in (int, float) and a != "":
            return False
        if type(b) is str and type(a) in (int, float) and b != "":
            return False
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-11
    return a == b


def _compute_irr_newton(cashflows: list[float], max_iter: int = 100) -> float | ExcelError:
    if len(cashflows) < 2:
        return ERR_VALUE
    arr = np.asarray(cashflows, dtype=np.float64)
    if not (np.any(arr < 0) and np.any(arr > 0)):
        return ERR_VALUE
    t = np.arange(arr.size, dtype=np.float64)
    r = 0.10
    for _ in range(max_iter):
        denom = np.power(1.0 + r, t)
        npv = float(np.sum(arr / denom))
        d_npv = float(np.sum(-t * arr / np.power(1.0 + r, t + 1.0)))
        if abs(d_npv) < 1e-14:
            break
        step = npv / d_npv
        r -= step
        if abs(step) < 1e-10:
            return float(r)
        r = max(-0.95, min(5.0, r))
    return float(r)


class EulrFormulaEngine:
    """Compiles EULR's Excel formulas into ASTs + reverse dependency graph for 10-pass solves."""

    def __init__(self, snapshot: EulrBaselineSnapshot) -> None:
        self.snapshot = snapshot
        self.named_map = self._build_named_range_map(snapshot)
        self.compiled_asts: dict[tuple[str, int, int], tuple[Any, ...]] = {}
        self.reverse_deps: dict[tuple[str, int, int], list[tuple[str, int, int]]] = {}
        self._compile_active_formulas()

    @staticmethod
    def _build_named_range_map(
        snapshot: EulrBaselineSnapshot,
    ) -> dict[tuple[str | None, str], tuple[str, int, int, int, int]]:
        out: dict[tuple[str | None, str], tuple[str, int, int, int, int]] = {}
        for nr in snapshot.named_ranges:
            name_u = nr["name"].strip().upper()
            attr = nr["attr_text"].strip().lstrip("=")
            scope = nr.get("scope_sheet")
            if "!" not in attr:
                continue
            sh_p, ref_p = attr.split("!", 1)
            sname = sh_p.strip("'")
            if sname not in snapshot.worksheets:
                continue
            try:
                if ":" in ref_p:
                    p1, p2 = ref_p.split(":", 1)
                    r1, c1 = split_a1_coord(p1)
                    r2, c2 = split_a1_coord(p2)
                    out[(scope, name_u)] = (sname, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))
                else:
                    r1, c1 = split_a1_coord(ref_p)
                    out[(scope, name_u)] = (sname, r1, c1, r1, c1)
            except ValueError:
                continue
        return out

    @staticmethod
    def _min_active_col_for_sheet(sheet_name: str) -> int:
        # Compile full horizon on compact analytical/carbon/HCK sheets, and 2020+ (Col AP=42) on 225-col history sheets
        if sheet_name in (
            "Carbon",
            "KeyInputs",
            "Yields",
            "Info",
            "ULSD-GO_spread_econs",
            "HCK naphtha revamp",
            "2015 NWE HCK IRR",
            "IMOfuels",
            "Links out",
        ):
            return 1
        return 42  # Col AP (2020) through Col 225 (2050+)

    def _compile_active_formulas(self) -> None:
        for sname, sh_cells in self.snapshot.cells_by_sheet.items():
            if sname == "UPLOAD":
                # UPLOAD (93,935 downstream staging cells) is materialized post-solve only when requested
                continue
            min_col = self._min_active_col_for_sheet(sname)
            for (r_idx, c_idx), tc in sh_cells.items():
                if tc.raw_formula is None or c_idx < min_col:
                    continue
                if tc.has_external_link or tc.is_array_cse:
                    # External links resolve via dt_external_links; {=CSE} rows evaluate via vectorized CSE helper
                    continue
                tokens = tokenize_excel_formula(tc.raw_formula)
                parser = _FormulaParser(tokens, sname, self.named_map)
                ast_node = parser.parse()
                key = (sname, r_idx, c_idx)
                self.compiled_asts[key] = ast_node
                for dep_key in parser.deps:
                    self.reverse_deps.setdefault(dep_key, []).append(key)

    def build_working_grid(
        self, upstream_mode: UpstreamMode = "baseline_cached"
    ) -> dict[str, dict[tuple[int, int], Any]]:
        """Create a mutable cell-value grid seeded with baseline (or 3-peer synced) values."""
        grid: dict[str, dict[tuple[int, int], Any]] = {}
        for sname, sh_cells in self.snapshot.cells_by_sheet.items():
            sh_vals: dict[tuple[int, int], Any] = {}
            for coord_rc, tc in sh_cells.items():
                if tc.data_type == "ERROR":
                    sh_vals[coord_rc] = ExcelError(tc.string_value or "#VALUE!")
                elif tc.numeric_value is not None:
                    sh_vals[coord_rc] = tc.numeric_value
                elif tc.string_value is not None:
                    sh_vals[coord_rc] = tc.string_value
            grid[sname] = sh_vals

        if upstream_mode == "peer_synced":
            for (sname, r_idx, c_idx), ext in self.snapshot.external_links.items():
                if ext.is_peer_updated and ext.peer_live_value is not None:
                    if sname in grid:
                        grid[sname][(r_idx, c_idx)] = ext.peer_live_value
        return grid

    def compute_affected_cone(
        self, seed_coords: set[tuple[str, int, int]]
    ) -> dict[str, list[tuple[int, int]]]:
        """BFS over reverse dependency edges to find all formula cells impacted by `seed_coords`."""
        visited: set[tuple[str, int, int]] = set()
        q: deque[tuple[str, int, int]] = deque(seed_coords)
        affected: dict[str, set[tuple[int, int]]] = {}

        while q:
            cur = q.popleft()
            for nxt in self.reverse_deps.get(cur, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    affected.setdefault(nxt[0], set()).add((nxt[1], nxt[2]))
                    q.append(nxt)

        return {sname: sorted(coords) for sname, coords in affected.items()}

    def eval_cell(
        self,
        grid: dict[str, dict[tuple[int, int], Any]],
        sheet_name: str,
        row_num: int,
        col_num: int,
    ) -> Any:
        ast_node = self.compiled_asts.get((sheet_name, row_num, col_num))
        if ast_node is None:
            return grid.get(sheet_name, {}).get((row_num, col_num), 0.0)
        return self._eval_node(ast_node, grid, sheet_name, row_num, col_num)

    def _get_range_matrix(
        self,
        grid: dict[str, dict[tuple[int, int], Any]],
        sname: str,
        r1: int,
        c1: int,
        r2: int,
        c2: int,
    ) -> list[list[Any]]:
        sh = grid.get(sname, {})
        return [
            [sh.get((rr, cc)) for cc in range(c1, c2 + 1)]
            for rr in range(r1, r2 + 1)
        ]

    def _resolve_ref_bounds(
        self, node: tuple[Any, ...], grid: dict[str, dict[tuple[int, int], Any]], cur_s: str, cur_r: int, cur_c: int
    ) -> tuple[str, int, int, int, int] | None:
        tag = node[0]
        if tag == "CELL":
            return (node[1], node[2], node[3], node[2], node[3])
        if tag == "RANGE":
            return (node[1], node[2], node[3], node[4], node[5])
        if tag == "CALL" and node[1] == "OFFSET":
            args = node[2]
            if len(args) >= 3:
                base_b = self._resolve_ref_bounds(args[0], grid, cur_s, cur_r, cur_c)
                if base_b is None:
                    return None
                dr = _to_float(self._eval_node(args[1], grid, cur_s, cur_r, cur_c))
                dc = _to_float(self._eval_node(args[2], grid, cur_s, cur_r, cur_c))
                if isinstance(dr, ExcelError) or isinstance(dc, ExcelError):
                    return None
                bs, br1, bc1, br2, bc2 = base_b
                h = (br2 - br1 + 1) if len(args) < 4 else int(round(float(_to_float(self._eval_node(args[3], grid, cur_s, cur_r, cur_c)) or 1)))  # type: ignore[arg-type]
                w = (bc2 - bc1 + 1) if len(args) < 5 else int(round(float(_to_float(self._eval_node(args[4], grid, cur_s, cur_r, cur_c)) or 1)))  # type: ignore[arg-type]
                nr1 = max(1, br1 + int(round(dr)))
                nc1 = max(1, bc1 + int(round(dc)))
                return (bs, nr1, nc1, nr1 + max(1, h) - 1, nc1 + max(1, w) - 1)
        return None

    def _eval_node(
        self,
        node: tuple[Any, ...],
        grid: dict[str, dict[tuple[int, int], Any]],
        cur_s: str,
        cur_r: int,
        cur_c: int,
    ) -> Any:
        tag = node[0]
        if tag in ("NUM", "STR", "BOOL", "ERR"):
            return node[1]
        if tag == "EXT_SELF":
            return grid.get(cur_s, {}).get((cur_r, cur_c), 0.0)
        if tag == "CELL":
            val = grid.get(node[1], {}).get((node[2], node[3]))
            return 0.0 if val is None else val
        if tag == "RANGE":
            return self._get_range_matrix(grid, node[1], node[2], node[3], node[4], node[5])
        if tag == "UNARY":
            v = _to_float(self._eval_node(node[2], grid, cur_s, cur_r, cur_c))
            return v if isinstance(v, ExcelError) else -v
        if tag == "BIN":
            op = node[1]
            lv = self._eval_node(node[2], grid, cur_s, cur_r, cur_c)
            if isinstance(lv, ExcelError):
                return lv
            rv = self._eval_node(node[3], grid, cur_s, cur_r, cur_c)
            if isinstance(rv, ExcelError):
                return rv
            if op == "&":
                s1 = "" if lv is None else str(lv)
                s2 = "" if rv is None else str(rv)
                return s1 + s2
            if op in ("=", "<>", "<", "<=", ">", ">="):
                if op == "=":
                    return _excel_eq(lv, rv)
                if op == "<>":
                    return not _excel_eq(lv, rv)
                lf = _to_float(lv)
                rf = _to_float(rv)
                if isinstance(lf, ExcelError) or isinstance(rf, ExcelError):
                    return str(lv) < str(rv) if op in ("<", "<=") else str(lv) > str(rv)
                if op == "<":
                    return lf < rf
                if op == "<=":
                    return lf <= rf
                if op == ">":
                    return lf > rf
                return lf >= rf

            lf = _to_float(lv)
            if isinstance(lf, ExcelError):
                return lf
            rf = _to_float(rv)
            if isinstance(rf, ExcelError):
                return rf
            if op == "+":
                return lf + rf
            if op == "-":
                return lf - rf
            if op == "*":
                return lf * rf
            if op == "/":
                return ERR_DIV0 if abs(rf) < 1e-15 else lf / rf
            if op == "^":
                try:
                    return float(lf**rf)
                except Exception:
                    return ERR_VALUE

        if tag == "CALL":
            fn = node[1]
            args: list[tuple[Any, ...]] = node[2]
            return self._eval_function(fn, args, grid, cur_s, cur_r, cur_c)

        return 0.0

    def _iter_numeric_args(
        self,
        args: list[tuple[Any, ...]],
        grid: dict[str, dict[tuple[int, int], Any]],
        cur_s: str,
        cur_r: int,
        cur_c: int,
    ) -> list[float] | ExcelError:
        nums: list[float] = []
        for a in args:
            rb = self._resolve_ref_bounds(a, grid, cur_s, cur_r, cur_c)
            if rb is not None:
                sh = grid.get(rb[0], {})
                for rr in range(rb[1], rb[3] + 1):
                    for cc in range(rb[2], rb[4] + 1):
                        v = sh.get((rr, cc))
                        if isinstance(v, ExcelError):
                            return v
                        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                            nums.append(float(v))
            else:
                ev = self._eval_node(a, grid, cur_s, cur_r, cur_c)
                if isinstance(ev, ExcelError):
                    return ev
                if isinstance(ev, list):
                    for row in ev:
                        for v in row:
                            if isinstance(v, ExcelError):
                                return v
                            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                                nums.append(float(v))
                else:
                    fv = _to_float(ev)
                    if isinstance(fv, ExcelError):
                        return fv
                    nums.append(fv)
        return nums

    def _eval_function(
        self,
        fn: str,
        args: list[tuple[Any, ...]],
        grid: dict[str, dict[tuple[int, int], Any]],
        cur_s: str,
        cur_r: int,
        cur_c: int,
    ) -> Any:
        if fn == "IF":
            if not args:
                return False
            cond = _to_bool(self._eval_node(args[0], grid, cur_s, cur_r, cur_c))
            if isinstance(cond, ExcelError):
                return cond
            if cond:
                return self._eval_node(args[1], grid, cur_s, cur_r, cur_c) if len(args) > 1 else True
            return self._eval_node(args[2], grid, cur_s, cur_r, cur_c) if len(args) > 2 else False

        if fn == "IFERROR":
            v = self._eval_node(args[0], grid, cur_s, cur_r, cur_c)
            if isinstance(v, ExcelError):
                return self._eval_node(args[1], grid, cur_s, cur_r, cur_c) if len(args) > 1 else 0.0
            return v

        if fn == "ISERROR":
            v = self._eval_node(args[0], grid, cur_s, cur_r, cur_c) if args else None
            return isinstance(v, ExcelError)

        if fn == "ISNUMBER":
            if not args:
                return False
            v = self._eval_node(args[0], grid, cur_s, cur_r, cur_c)
            return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

        if fn in ("AND", "OR"):
            acc = fn == "AND"
            for a in args:
                b = _to_bool(self._eval_node(a, grid, cur_s, cur_r, cur_c))
                if isinstance(b, ExcelError):
                    return b
                if fn == "AND" and not b:
                    return False
                if fn == "OR" and b:
                    return True
            return acc

        if fn in ("SUM", "AVERAGE", "MIN", "MAX"):
            nums = self._iter_numeric_args(args, grid, cur_s, cur_r, cur_c)
            if isinstance(nums, ExcelError):
                return nums
            if fn == "SUM":
                return float(sum(nums))
            if not nums:
                return ERR_DIV0 if fn == "AVERAGE" else 0.0
            if fn == "AVERAGE":
                return float(sum(nums) / len(nums))
            if fn == "MIN":
                return float(min(nums))
            return float(max(nums))

        if fn == "SUMPRODUCT":
            if not args:
                return 0.0
            mats: list[list[float]] = []
            for a in args:
                rb = self._resolve_ref_bounds(a, grid, cur_s, cur_r, cur_c)
                flat: list[float] = []
                if rb is not None:
                    sh = grid.get(rb[0], {})
                    for rr in range(rb[1], rb[3] + 1):
                        for cc in range(rb[2], rb[4] + 1):
                            v = sh.get((rr, cc))
                            if isinstance(v, ExcelError):
                                return v
                            flat.append(
                                float(v)
                                if isinstance(v, (int, float)) and not isinstance(v, bool)
                                else 0.0
                            )
                else:
                    ev = self._eval_node(a, grid, cur_s, cur_r, cur_c)
                    if isinstance(ev, ExcelError):
                        return ev
                    if isinstance(ev, list):
                        for row in ev:
                            for v in row:
                                if isinstance(v, ExcelError):
                                    return v
                                flat.append(
                                    float(v)
                                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                                    else 0.0
                                )
                    else:
                        fv = _to_float(ev)
                        flat.append(0.0 if isinstance(fv, ExcelError) else fv)
                mats.append(flat)
            min_len = min(len(m) for m in mats)
            if min_len == 0:
                return 0.0
            total = 0.0
            for idx in range(min_len):
                prod = 1.0
                for m in mats:
                    prod *= m[idx]
                total += prod
            return float(total)

        if fn == "OFFSET":
            rb = self._resolve_ref_bounds(("CALL", "OFFSET", args), grid, cur_s, cur_r, cur_c)
            if rb is None:
                return ERR_REF
            if rb[1] == rb[3] and rb[2] == rb[4]:
                val = grid.get(rb[0], {}).get((rb[1], rb[2]))
                return 0.0 if val is None else val
            return self._get_range_matrix(grid, rb[0], rb[1], rb[2], rb[3], rb[4])

        if fn == "COLUMN":
            if not args:
                return float(cur_c)
            rb = self._resolve_ref_bounds(args[0], grid, cur_s, cur_r, cur_c)
            return float(rb[2]) if rb is not None else float(cur_c)

        if fn == "VLOOKUP":
            if len(args) < 3:
                return ERR_NA
            key = self._eval_node(args[0], grid, cur_s, cur_r, cur_c)
            rb = self._resolve_ref_bounds(args[1], grid, cur_s, cur_r, cur_c)
            col_idx = _to_float(self._eval_node(args[2], grid, cur_s, cur_r, cur_c))
            exact = False
            if len(args) >= 4:
                eb = _to_bool(self._eval_node(args[3], grid, cur_s, cur_r, cur_c))
                exact = False if isinstance(eb, ExcelError) else (not eb)
            if rb is None or isinstance(col_idx, ExcelError):
                return ERR_NA
            target_c = rb[2] + int(round(col_idx)) - 1
            if target_c > rb[4]:
                return ERR_REF
            sh = grid.get(rb[0], {})
            best_r: int | None = None
            for rr in range(rb[1], rb[3] + 1):
                cand = sh.get((rr, rb[2]))
                if _excel_eq(cand, key):
                    v = sh.get((rr, target_c))
                    return 0.0 if v is None else v
                if not exact and isinstance(cand, (int, float)) and isinstance(key, (int, float)):
                    if cand <= key:
                        best_r = rr
            if not exact and best_r is not None:
                v = sh.get((best_r, target_c))
                return 0.0 if v is None else v
            return ERR_NA

        if fn == "HLOOKUP":
            if len(args) < 3:
                return ERR_NA
            key = self._eval_node(args[0], grid, cur_s, cur_r, cur_c)
            rb = self._resolve_ref_bounds(args[1], grid, cur_s, cur_r, cur_c)
            row_idx = _to_float(self._eval_node(args[2], grid, cur_s, cur_r, cur_c))
            exact = False
            if len(args) >= 4:
                eb = _to_bool(self._eval_node(args[3], grid, cur_s, cur_r, cur_c))
                exact = not bool(eb)
            if rb is None or isinstance(row_idx, ExcelError):
                return ERR_NA
            target_r = rb[1] + int(round(row_idx)) - 1
            if target_r > rb[3]:
                return ERR_REF
            sh = grid.get(rb[0], {})
            best_c: int | None = None
            for cc in range(rb[2], rb[4] + 1):
                cand = sh.get((rb[1], cc))
                if _excel_eq(cand, key):
                    v = sh.get((target_r, cc))
                    return 0.0 if v is None else v
                if not exact and isinstance(cand, (int, float)) and isinstance(key, (int, float)):
                    if cand <= key:
                        best_c = cc
            if not exact and best_c is not None:
                v = sh.get((target_r, best_c))
                return 0.0 if v is None else v
            return ERR_NA

        if fn == "INDEX":
            if len(args) < 2:
                return ERR_REF
            rb = self._resolve_ref_bounds(args[0], grid, cur_s, cur_r, cur_c)
            r_off = _to_float(self._eval_node(args[1], grid, cur_s, cur_r, cur_c))
            c_off = (
                _to_float(self._eval_node(args[2], grid, cur_s, cur_r, cur_c))
                if len(args) >= 3
                else 1.0
            )
            if rb is None or isinstance(r_off, ExcelError) or isinstance(c_off, ExcelError):
                return ERR_REF
            rr = rb[1] + max(0, int(round(r_off)) - 1)
            cc = rb[2] + max(0, int(round(c_off)) - 1)
            v = grid.get(rb[0], {}).get((rr, cc))
            return 0.0 if v is None else v

        if fn == "IRR":
            if not args:
                return ERR_VALUE
            nums = self._iter_numeric_args([args[0]], grid, cur_s, cur_r, cur_c)
            if isinstance(nums, ExcelError):
                return nums
            return _compute_irr_newton(nums)

        if fn == "TREND":
            if not args:
                return 0.0
            ys = self._iter_numeric_args([args[0]], grid, cur_s, cur_r, cur_c)
            if isinstance(ys, ExcelError) or len(ys) == 0:
                return ERR_VALUE
            xs = (
                self._iter_numeric_args([args[1]], grid, cur_s, cur_r, cur_c)
                if len(args) >= 2
                else [float(i + 1) for i in range(len(ys))]
            )
            if isinstance(xs, ExcelError) or len(xs) != len(ys):
                xs = [float(i + 1) for i in range(len(ys))]
            nx = (
                _to_float(self._eval_node(args[2], grid, cur_s, cur_r, cur_c))
                if len(args) >= 3
                else float(len(ys) + 1)
            )
            if isinstance(nx, ExcelError):
                return nx
            if len(ys) == 1:
                return ys[0]
            slope, intercept = np.polyfit(np.asarray(xs), np.asarray(ys), 1)
            return float(slope * nx + intercept)

        if fn == "ROUND":
            v = _to_float(self._eval_node(args[0], grid, cur_s, cur_r, cur_c))
            d = _to_float(self._eval_node(args[1], grid, cur_s, cur_r, cur_c)) if len(args) > 1 else 0.0
            if isinstance(v, ExcelError) or isinstance(d, ExcelError):
                return ERR_VALUE
            return round(v, int(round(d)))

        if fn == "ROUNDDOWN":
            v = _to_float(self._eval_node(args[0], grid, cur_s, cur_r, cur_c))
            d = _to_float(self._eval_node(args[1], grid, cur_s, cur_r, cur_c)) if len(args) > 1 else 0.0
            if isinstance(v, ExcelError) or isinstance(d, ExcelError):
                return ERR_VALUE
            factor = 10.0 ** int(round(d))
            return math.trunc(v * factor) / factor

        if fn == "CONCATENATE":
            parts: list[str] = []
            for a in args:
                ev = self._eval_node(a, grid, cur_s, cur_r, cur_c)
                if isinstance(ev, ExcelError):
                    return ev
                parts.append("" if ev is None else str(ev))
            return "".join(parts)

        if fn == "LEFT":
            s = str(self._eval_node(args[0], grid, cur_s, cur_r, cur_c) or "")
            n = int(round(float(_to_float(self._eval_node(args[1], grid, cur_s, cur_r, cur_c)) if len(args) > 1 else 1.0)))  # type: ignore[arg-type]
            return s[: max(0, n)]

        if fn == "DATE":
            y = int(round(float(_to_float(self._eval_node(args[0], grid, cur_s, cur_r, cur_c)) or 1990)))  # type: ignore[arg-type]
            m = int(round(float(_to_float(self._eval_node(args[1], grid, cur_s, cur_r, cur_c)) or 1)))  # type: ignore[arg-type]
            d = int(round(float(_to_float(self._eval_node(args[2], grid, cur_s, cur_r, cur_c)) or 1)))  # type: ignore[arg-type]
            epoch = dt.date(1899, 12, 30)
            return float((dt.date(y, max(1, min(12, m)), max(1, min(28, d))) - epoch).days)

        if fn == "YEAR":
            serial = _to_float(self._eval_node(args[0], grid, cur_s, cur_r, cur_c))
            if isinstance(serial, ExcelError):
                return serial
            d_obj = dt.date(1899, 12, 30) + dt.timedelta(days=int(round(serial)))
            return float(d_obj.year)

        if fn == "TODAY":
            return float((dt.date.today() - dt.date(1899, 12, 30)).days)

        if fn in ("CELL", "TRANSPOSE"):
            return grid.get(cur_s, {}).get((cur_r, cur_c), 0.0)

        return grid.get(cur_s, {}).get((cur_r, cur_c), 0.0)
