"""ECharts v5 & Excel-Coordinate Markdown Renderer for Latinlr202409 Digital Twin."""

from __future__ import annotations

from typing import Any


def fmt_num(val: Any, digits: int = 2) -> str:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return f"{val:,.{digits}f}"
    return "—" if val is None else str(val)


def render_milestone_markdown_table(
    title: str,
    rows: list[dict[str, Any]],
    years: list[int],
    digits: int = 2,
) -> str:
    """Render an Excel-layout milestone table (`Metric | Sheet!Row | Units | 2024 | ... | 2050`)."""
    yr_hdr = " | ".join(str(y) for y in years)
    yr_sep = " | ".join("---:" for _ in years)
    lines = [
        f"## {title}",
        "",
        f"| Metric | Sheet!Row | Units | {yr_hdr} |",
        f"| :--- | :--- | :---: | {yr_sep} |",
    ]
    for r in rows:
        vals = r.get("values") or {}
        cells = " | ".join(fmt_num(vals.get(y, vals.get(str(y))), digits) for y in years)
        lines.append(
            f"| **{r.get('metric', r.get('label', ''))}** | `{r.get('coord', '')}` | "
            f"{r.get('units', '')} | {cells} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_line_echarts_option(
    title: str,
    y_axis_name: str,
    years: list[int],
    series_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build Apache ECharts v5 multi-series line trajectory specification."""
    series: list[dict[str, Any]] = []
    legend: list[str] = []
    for row in series_rows:
        name = str(row.get("metric") or row.get("label") or "Series")
        vals = row.get("values") or {}
        legend.append(name)
        series.append(
            {
                "name": name,
                "type": "line",
                "smooth": True,
                "data": [vals.get(y, vals.get(str(y))) for y in years],
            }
        )
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "data": legend},
        "grid": {"left": "8%", "right": "4%", "top": "14%", "bottom": "18%"},
        "xAxis": {"type": "category", "data": [str(y) for y in years]},
        "yAxis": {"type": "value", "name": y_axis_name},
        "series": series,
    }


def build_bar_comparison_echarts_option(
    title: str,
    y_axis_name: str,
    categories: list[str],
    series_map: dict[str, list[float | None]],
) -> dict[str, Any]:
    """Build Apache ECharts v5 grouped bar comparison chart (scenario matrix / assay economics)."""
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0, "data": list(series_map.keys())},
        "grid": {"left": "8%", "right": "4%", "top": "14%", "bottom": "20%"},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 15}},
        "yAxis": {"type": "value", "name": y_axis_name},
        "series": [
            {"name": name, "type": "bar", "data": data}
            for name, data in series_map.items()
        ],
    }
