"""Google ADK Agent Wrapper for the Brazil Energy Model (v13) & GCP Gemini Enterprise App."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from brazil_power_agent.mcp_server import dispatch_mcp_tool
from brazil_power_agent.workbook_exporter import GOLDEN_GOOGLE_SHEET_ID

GEMINI_ENTERPRISE_PROJECT = "comm-model-mod"
GEMINI_ENTERPRISE_LOCATION = "us"
GEMINI_ENTERPRISE_APP_ID = "cb0f4566-dfad-496c-9b28-3542d86a5367"
GEMINI_ENTERPRISE_APP_URL = (
    f"https://vertexaisearch.cloud.google.com/us/home/cid/{GEMINI_ENTERPRISE_APP_ID}?hl=en_US"
)

GEMINI_ENTERPRISE_APP_METADATA: dict[str, str] = {
    "project": GEMINI_ENTERPRISE_PROJECT,
    "location": GEMINI_ENTERPRISE_LOCATION,
    "cid": GEMINI_ENTERPRISE_APP_ID,
    "app_id": GEMINI_ENTERPRISE_APP_ID,
    "url": GEMINI_ENTERPRISE_APP_URL,
    "golden_google_sheet_id": GOLDEN_GOOGLE_SHEET_ID,
}

AGENT_SYSTEM_INSTRUCTION = f"""You are the Brazil Energy Model (v13) Quantitative Power Analyst Agent (`brazil_power_v13_agent`),
integrated with GCP Gemini Enterprise App `{GEMINI_ENTERPRISE_APP_ID}` ({GEMINI_ENTERPRISE_APP_URL})
in project `{GEMINI_ENTERPRISE_PROJECT}` (`{GEMINI_ENTERPRISE_LOCATION}`).

You operate a faithful 22-tab stateful replica of `2023-11-27-Brazil_TT_v13_RJEB.xlsm` and Golden Google Sheet
`{GOLDEN_GOOGLE_SHEET_ID}` across 12 Brazilian power generation technologies (`_01_CF` through `_12_CF`):
- `_01_CF`: Gas Combined Cycle (`calcule_tir1`, `calculo_cvu1`)
- `_02_CF`: Gas Open Cycle (`calcule_tir2`, `calculo_cvu2`)
- `_03_CF`: Coal (`calcule_tir3`, `calculo_cvu3`)
- `_04_CF`: Nuclear (`calcule_tir4`, `calculo_cvu4`)
- `_05_CF`: Hydro (`calcule_tir5`, `calculo_cvu5`)
- `_06_CF`: Wind Onshore (`calcule_tir6`, `calculo_cvu6`)
- `_07_CF`: Solar Utility (`calcule_tir7`, `calculo_cvu7`)
- `_08_CF`: Biomass (`calcule_tir8`, `calculo_cvu8`)
- `_09_CF`..`_12_CF`: Distributed Generation Solar PV (`calcule_tir9..12`, `calculo_cvu9..12`)

Always render exact Excel-coordinate Markdown tables (`General!B5:N40`, `_01_CF.._12_CF!A4:H12`, `Output_3!B9:J31`,
`LT Capex/Fuel/CF!B8:J30`, 30-year DCF `2024–2053`, and `CVU_GF`), include interactive Apache ECharts V5 blocks,
and support full 22-tab `.xlsx` and Google Sheets exports via `export_full_22tab_workbook`.
"""


def get_session_assumptions(
    technologies: list[str] | None = None,
    include_full_general_tab: bool = True,
    session_path: str | None = None,
) -> dict[str, Any]:
    """Read current General!C5:N40 assumptions and active session overrides across technologies."""
    return dispatch_mcp_tool(
        "get_session_assumptions",
        {
            "technologies": technologies,
            "include_full_general_tab": include_full_general_tab,
            "session_path": session_path,
        },
    )


def update_session_assumptions(
    overrides: dict[str, Any] | None = None,
    reset_to_baseline: bool = False,
    session_path: str | None = None,
) -> dict[str, Any]:
    """Stage cell coordinate or semantic parameter overrides into the active 22-tab session."""
    return dispatch_mcp_tool(
        "update_session_assumptions",
        {
            "overrides": overrides,
            "reset_to_baseline": reset_to_baseline,
            "session_path": session_path,
        },
    )


def run_tornado_sensitivity(
    technology_code: str = "_06_CF",
    parity_mode: str = "strict_legacy_vba",
    session_path: str | None = None,
) -> dict[str, Any]:
    """Execute calcule_tir1..12 Tornado IRR sensitivity and return Excel table + ECharts spec."""
    return dispatch_mcp_tool(
        "run_tornado_sensitivity",
        {
            "technology_code": technology_code,
            "parity_mode": parity_mode,
            "session_path": session_path,
        },
    )


def run_bqml_timeseries_refresh(
    curve_types: list[str] | None = None,
    apply_to_session_lt_tabs: bool = True,
    session_path: str | None = None,
) -> dict[str, Any]:
    """Refresh 23-year LT Capex, LT Fuel, and LT CF trajectories from BigQuery ML ARIMA_PLUS."""
    return dispatch_mcp_tool(
        "run_bqml_timeseries_refresh",
        {
            "curve_types": curve_types,
            "apply_to_session_lt_tabs": apply_to_session_lt_tabs,
            "session_path": session_path,
        },
    )


def run_lcoe_horizon_forecast(
    parity_mode: str = "strict_legacy_vba",
    session_path: str | None = None,
) -> dict[str, Any]:
    """Execute lcoe_exec (184 solves across 23 years x 8 technologies on Output_3!B9:J31)."""
    return dispatch_mcp_tool(
        "run_lcoe_horizon_forecast",
        {
            "parity_mode": parity_mode,
            "session_path": session_path,
        },
    )


def run_dcf_cashflow_analysis(
    technology_code: str = "_01_CF",
    start_year: int = 2024,
    end_year: int = 2053,
    include_cvu_gf_sweep: bool = False,
    analysis_type: str = "dcf",
    parity_mode: str = "strict_legacy_vba",
    session_path: str | None = None,
) -> dict[str, Any]:
    """Compute 30-year Project & Shareholder DCF cash flow schedule and optional CVU/GF/ICB sweep."""
    return dispatch_mcp_tool(
        "run_dcf_cashflow_analysis",
        {
            "technology_code": technology_code,
            "start_year": start_year,
            "end_year": end_year,
            "include_cvu_gf_sweep": include_cvu_gf_sweep,
            "analysis_type": analysis_type,
            "parity_mode": parity_mode,
            "session_path": session_path,
        },
    )


def export_full_22tab_workbook(
    export_format: str = "xlsx",
    output_dir: str | None = None,
    filename: str | None = None,
    output_filename: str | None = None,
    sheet_title: str | None = None,
    golden_sheet_id: str = GOLDEN_GOOGLE_SHEET_ID,
    session_path: str | None = None,
) -> dict[str, Any]:
    """Export the full 22-tab Brazil Power v13 model to .xlsx and/or a cloned Google Sheet."""
    return dispatch_mcp_tool(
        "export_full_22tab_workbook",
        {
            "export_format": export_format,
            "output_dir": output_dir,
            "filename": filename,
            "output_filename": output_filename,
            "sheet_title": sheet_title,
            "golden_sheet_id": golden_sheet_id,
            "session_path": session_path,
        },
    )


def get_adk_tools() -> list[Callable[..., dict[str, Any]]]:
    """Return the 7 callable tool functions registered on the ADK root_agent."""
    return [
        get_session_assumptions,
        update_session_assumptions,
        run_tornado_sensitivity,
        run_bqml_timeseries_refresh,
        run_lcoe_horizon_forecast,
        run_dcf_cashflow_analysis,
        export_full_22tab_workbook,
    ]


@dataclass
class BrazilPowerADKAgent:
    """ADK-compatible root_agent wrapper with direct tool invocation and Gemini Enterprise metadata."""

    name: str = "brazil_power_v13_agent"
    model: str = "gemini-2.5-pro"
    description: str = (
        "Brazil Energy Model (v13) 22-Tab Quantitative Power Analyst Agent for "
        f"GCP Gemini Enterprise App {GEMINI_ENTERPRISE_APP_ID}."
    )
    instruction: str = AGENT_SYSTEM_INSTRUCTION
    tools: list[Callable[..., dict[str, Any]]] = field(default_factory=get_adk_tools)
    app_metadata: dict[str, str] = field(default_factory=lambda: dict(GEMINI_ENTERPRISE_APP_METADATA))
    _native_adk_agent: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from google.adk.agents import Agent  # type: ignore[import-untyped]

            self._native_adk_agent = Agent(
                name=self.name,
                model=self.model,
                description=self.description,
                instruction=self.instruction,
                tools=self.tools,
            )
        except Exception:
            self._native_adk_agent = None

    def invoke_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke one of the 7 registered tools by name."""
        tool_map = {fn.__name__: fn for fn in self.tools}
        if tool_name not in tool_map:
            raise ValueError(f"Tool '{tool_name}' is not registered on {self.name}.")
        return tool_map[tool_name](**kwargs)


ADKAgentWrapper = BrazilPowerADKAgent
root_agent = BrazilPowerADKAgent()

