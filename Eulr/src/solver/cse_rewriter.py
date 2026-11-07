"""Vectorized NumPy evaluators for the 6,740 Op_Cost {=CSE} interpolation formulas, 5 IRR cells, and pre-1990 error sentinels."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CSERewriteStats:
    total_cse_cells: int = 6745
    op_cost_cse_cells: int = 6135
    pricing_cse_cells: int = 605
    input_and_upload_cse_cells: int = 6
    hck_irr_cells: int = 5
    pre_1990_error_sentinel_cells: int = 280


def interpolate_op_cost_row(row_values: np.ndarray) -> np.ndarray:
    """
    Vectorized replacement for the 6,740 Op_Cost {=CSE} lookahead interpolation formulas:
    {=IF(MIN(IF(ISNUMBER(RC[1]:RC52),COLUMN(RC[1]:RC52)))>0, ...)}
    Replaces NaN gaps between valid anchor columns using linear forward-index interpolation.
    """
    arr = np.array(row_values, dtype=np.float64, copy=True)
    valid_mask = np.isfinite(arr)
    if valid_mask.sum() < 2 or valid_mask.all():
        return arr

    valid_indices = np.flatnonzero(valid_mask)
    first_idx, last_idx = int(valid_indices[0]), int(valid_indices[-1])
    if last_idx > first_idx:
        span = np.arange(first_idx, last_idx + 1, dtype=np.float64)
        arr[first_idx : last_idx + 1] = np.interp(
            span,
            valid_indices.astype(np.float64),
            arr[valid_indices],
        )
    return arr


def compute_cashflow_irr(cashflows: list[float] | np.ndarray, max_iter: int = 100) -> float:
    """
    Newton-Raphson IRR solver replacing Excel's IRR() on '2015 NWE HCK IRR'.
    """
    cf = np.asarray(cashflows, dtype=np.float64)
    if cf.size < 2 or not (np.any(cf < 0) and np.any(cf > 0)):
        return 0.0

    t = np.arange(cf.size, dtype=np.float64)
    r = 0.10
    for _ in range(max_iter):
        denom = np.power(1.0 + r, t)
        npv = float(np.sum(cf / denom))
        d_npv = float(np.sum(-t * cf / np.power(1.0 + r, t + 1.0)))
        if abs(d_npv) < 1e-14:
            break
        step = npv / d_npv
        r -= step
        if abs(step) < 1e-10:
            break
        r = max(-0.95, min(5.0, r))
    return float(r)


def isolate_pre1990_error_sentinels(tensor: np.ndarray, error_coords: list[tuple[int, int]]) -> np.ndarray:
    """
    Isolate the 280 pre-1990 (#DIV/0!, #REF!, #VALUE!, #N/A) error cells using IEEE-754 NaN
    so 1990-2050+ forecast columns evaluate without contamination.
    """
    out = tensor.copy()
    for r_idx, c_idx in error_coords:
        if 0 <= r_idx < out.shape[0] and 0 <= c_idx < out.shape[1]:
            out[r_idx, c_idx] = np.nan
    return out
