"""BigQuery Remote Function batch handler for fn_solve_lcoe (/v1/bqml/solve)."""

from __future__ import annotations

import json
from typing import Any

from src.schemas.solver import (
    BQMLRemoteFunctionRequest,
    BQMLRemoteFunctionResponse,
    SolveMacroRequest,
)
from src.solver.macros.registry import MacroExecutionRegistry


def handle_bqml_remote_calls(request: BQMLRemoteFunctionRequest) -> BQMLRemoteFunctionResponse:
    """Process a batch of BigQuery Remote Function calls: [[macro_name, payload_json], ...]."""
    replies: list[Any] = []
    try:
        for call_args in request.calls:
            if not call_args:
                replies.append({"error": "Empty call arguments"})
                continue
            macro_name = str(call_args[0])
            raw_payload = call_args[1] if len(call_args) > 1 else {}
            if isinstance(raw_payload, str) and raw_payload.strip():
                payload_dict = json.loads(raw_payload)
            elif isinstance(raw_payload, dict):
                payload_dict = raw_payload
            else:
                payload_dict = {}

            solve_req = SolveMacroRequest(
                macro_name=macro_name,
                workbook_id=payload_dict.get(
                    "workbook_id", "Regional Power Generation Techno-Economic Model"
                ),
                spreadsheet_id=payload_dict.get("spreadsheet_id", "bqml-remote-fn"),
                sheet_inputs=payload_dict.get("sheet_inputs", {}),
                parity_mode=payload_dict.get("parity_mode", "strict_legacy_vba"),
            )
            res = MacroExecutionRegistry.execute(solve_req)
            replies.append(
                {
                    "macro_name": res.macro_name,
                    "solve_count": res.solve_count,
                    "execution_time_ms": round(res.execution_time_ms, 3),
                    "flat_outputs": res.flat_outputs,
                }
            )
        return BQMLRemoteFunctionResponse(replies=replies)
    except Exception as exc:  # noqa: BLE001
        return BQMLRemoteFunctionResponse(replies=[], errorMessage=str(exc))
