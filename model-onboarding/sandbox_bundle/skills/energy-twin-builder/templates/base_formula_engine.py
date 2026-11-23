"""Workbook-agnostic deterministic Excel Formula Tokenizer & Core Function Helpers (zero `eval()`)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np


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


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


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


def excel_npv(rate: float, cashflows: list[float]) -> float:
    """Compute Excel-compatible NPV(rate, cf1, cf2, ...)."""
    if rate <= -1.0:
        return float("nan")
    return float(sum(cf / ((1.0 + rate) ** (idx + 1)) for idx, cf in enumerate(cashflows)))


def excel_irr(cashflows: list[float], guess: float = 0.1, max_iter: int = 100, tol: float = 1e-7) -> float:
    """Compute deterministic IRR via damped Newton-Raphson with bisection fallback."""
    arr = np.asarray(cashflows, dtype=float)
    if arr.size < 2 or not (np.any(arr > 0) and np.any(arr < 0)):
        return float("nan")

    periods = np.arange(arr.size, dtype=float)
    r = guess
    for _ in range(max_iter):
        denom = (1.0 + r) ** periods
        f_val = float(np.sum(arr / denom))
        if abs(f_val) <= tol:
            return r
        df_val = float(np.sum(-periods * arr / ((1.0 + r) ** (periods + 1.0))))
        if abs(df_val) < 1e-12 or not math.isfinite(df_val):
            break
        r_next = max(-0.95, min(10.0, r - f_val / df_val))
        if abs(r_next - r) <= tol:
            return r_next
        r = r_next

    lo, hi = -0.90, 5.0
    f_lo = float(np.sum(arr / ((1.0 + lo) ** periods)))
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        f_mid = float(np.sum(arr / ((1.0 + mid) ** periods)))
        if abs(f_mid) <= tol or (hi - lo) <= tol:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
