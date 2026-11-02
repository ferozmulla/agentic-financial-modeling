"""CLI runner to execute any or all of the 38 quantitative macros and verify numerical parity."""

from __future__ import annotations

import argparse
import json

from src.schemas.solver import SolveMacroRequest
from src.solver.macros.registry import MacroExecutionRegistry
from src.solver.workbook_context import get_baseline_solver_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Run vectorized quantitative solver macros.")
    parser.add_argument(
        "--macro",
        default="all",
        help="Macro name to execute (e.g., lcoe_exec, calcule_tir1) or 'all'",
    )
    args = parser.parse_args()

    ctx = get_baseline_solver_context()
    macros_to_run = (
        MacroExecutionRegistry.list_supported_macros()
        if args.macro == "all"
        else [args.macro]
    )

    total_solves = 0
    max_rel_err = 0.0
    for mname in macros_to_run:
        res = MacroExecutionRegistry.execute(SolveMacroRequest(macro_name=mname), base_context=ctx)
        total_solves += res.solve_count
        expected_flat = ctx.macros.get(mname, {}).get("flat_outputs", {})
        for coord, exp_val in expected_flat.items():
            if isinstance(exp_val, (int, float)) and coord in res.flat_outputs:
                act_val = float(res.flat_outputs[coord])
                rel_err = abs(act_val - float(exp_val)) / max(abs(float(exp_val)), 1e-12)
                max_rel_err = max(max_rel_err, rel_err)

    print(
        json.dumps(
            {
                "executed_macros": len(macros_to_run),
                "total_solve_points": total_solves,
                "max_relative_error": max_rel_err,
                "parity_gate_passed": max_rel_err <= 1e-8,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
