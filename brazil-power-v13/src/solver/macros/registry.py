"""MacroExecutionRegistry dispatching all 38 ported routines (31 button macros + 7 helpers)."""

from __future__ import annotations

from typing import ClassVar

from src.schemas.solver import SolveMacroRequest, SolveMacroResponse
from src.solver.macros.cvu_sweeps import execute_cvu_sweep_macro
from src.solver.macros.forecasts_and_dispatch import (
    execute_fator_i,
    execute_helper_routine,
    execute_lcoe_exec,
    execute_lcoe_forecast,
)
from src.solver.macros.sensitivity_1d_2d import (
    SPECIALIZED_MATRIX_CONFIGS,
    execute_specialized_sensitivity_macro,
)
from src.solver.macros.tornado_irr import execute_tornado_macro
from src.solver.workbook_context import WorkbookSolverContext, get_baseline_solver_context


class MacroExecutionRegistry:
    """Central registry and dispatcher for all 38 ported quantitative routines."""

    TORNADO_MACROS: ClassVar[dict[str, int]] = {f"calcule_tir{i}": i for i in range(1, 13)}
    CVU_MACROS: ClassVar[dict[str, int]] = {f"calculo_cvu{i}": i for i in range(1, 13)}
    SPECIALIZED_MACROS: ClassVar[frozenset[str]] = frozenset(SPECIALIZED_MATRIX_CONFIGS.keys())
    HELPER_MACROS: ClassVar[frozenset[str]] = frozenset(
        {"rst_scenario", "iter_conv", "iter_refining", "iter_conv_gd", "iter_refining_gd"}
    )

    @classmethod
    def list_supported_macros(cls) -> list[str]:
        """Return sorted list of all 38 supported macro names."""
        all_names = (
            set(cls.TORNADO_MACROS.keys())
            | set(cls.CVU_MACROS.keys())
            | cls.SPECIALIZED_MACROS
            | {"lcoe_exec", "lcoe_forecast", "fator_i"}
            | cls.HELPER_MACROS
        )
        return sorted(all_names)

    @classmethod
    def execute(
        cls,
        request: SolveMacroRequest,
        base_context: WorkbookSolverContext | None = None,
    ) -> SolveMacroResponse:
        """Execute any of the 38 quantitative routines against an isolated WorkbookSolverContext."""
        macro_name = request.macro_name.strip()
        ctx_root = base_context or get_baseline_solver_context()
        ctx = ctx_root.clone_with_overrides(
            general_overrides=request.general_overrides,
            sheet_inputs=request.sheet_inputs,
        )

        if macro_name in cls.TORNADO_MACROS:
            return execute_tornado_macro(
                macro_name=macro_name,
                tech_index=cls.TORNADO_MACROS[macro_name],
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        if macro_name in cls.CVU_MACROS:
            return execute_cvu_sweep_macro(
                macro_name=macro_name,
                tech_index=cls.CVU_MACROS[macro_name],
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        if macro_name in cls.SPECIALIZED_MACROS:
            return execute_specialized_sensitivity_macro(
                macro_name=macro_name,
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        if macro_name == "lcoe_exec":
            return execute_lcoe_exec(
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        if macro_name == "lcoe_forecast":
            return execute_lcoe_forecast(
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        if macro_name == "fator_i":
            return execute_fator_i(
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        if macro_name in cls.HELPER_MACROS:
            return execute_helper_routine(
                macro_name=macro_name,
                context=ctx,
                workbook_id=request.workbook_id,
                spreadsheet_id=request.spreadsheet_id,
                parity_mode=request.parity_mode,
            )

        raise ValueError(
            f"Unsupported or deprecated macro '{macro_name}'. "
            f"Supported macros ({len(cls.list_supported_macros())}): {cls.list_supported_macros()}"
        )
