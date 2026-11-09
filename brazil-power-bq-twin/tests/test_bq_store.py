"""Unit tests for InMemoryDigitalTwinStore and parameterized BigQueryDigitalTwinStore."""

from __future__ import annotations

import json
from typing import Any

from brazil_power_bq_twin.bq_store import (
    BigQueryDigitalTwinStore,
    InMemoryDigitalTwinStore,
    resolve_effective_cell_value,
    resolve_effective_grid,
)
from brazil_power_bq_twin.config import TwinSettings
from brazil_power_bq_twin.models import (
    BaselineTwinSnapshot,
    CellDelta,
    CellRecord,
    StyleRecord,
    WorksheetRecord,
)


def _sample_snapshot() -> BaselineTwinSnapshot:
    return BaselineTwinSnapshot(
        workbook_id="brazil_power_v13",
        version_id="v13_baseline",
        version_label="Brazil Power v13 Seed",
        worksheets=[WorksheetRecord(sheet_index=0, sheet_name="General")],
        styles={0: StyleRecord(style_id=0)},
        cells_by_sheet={
            "General": {
                "C20": CellRecord(
                    sheet_name="General",
                    cell_coord="C20",
                    row_num=20,
                    col_num=3,
                    data_type="n",
                    numeric_value=4.50,
                    semantic_role="INPUT",
                ),
                "D20": CellRecord(
                    sheet_name="General",
                    cell_coord="D20",
                    row_num=20,
                    col_num=4,
                    data_type="n",
                    numeric_value=35.0,
                    semantic_role="INPUT",
                ),
            }
        },
    )


def test_in_memory_store_overlay_and_reset() -> None:
    snap = _sample_snapshot()
    store = InMemoryDigitalTwinStore(snap)

    overlay0 = store.get_session_overlay("sess_a")
    assert resolve_effective_cell_value(snap, overlay0, "General", "C20") == 4.50

    store.append_session_deltas(
        "sess_a",
        [
            CellDelta(
                sheet_name="General",
                cell_coord="C20",
                row_num=20,
                col_num=3,
                delta_kind="USER_OVERRIDE",
                numeric_value=6.50,
                source_tool="update_session_assumptions",
            )
        ],
    )
    overlay1 = store.get_session_overlay("sess_a")
    assert resolve_effective_cell_value(snap, overlay1, "General", "C20") == 6.50
    grid = resolve_effective_grid(snap, overlay1, "General", "C20", "D20")
    assert grid == [[6.50, 35.0]]

    # Other sessions remain isolated
    other = store.get_session_overlay("sess_b")
    assert resolve_effective_cell_value(snap, other, "General", "C20") == 4.50

    # Reset restores baseline via RESET_TOMBSTONE
    store.reset_session("sess_a")
    overlay2 = store.get_session_overlay("sess_a")
    assert resolve_effective_cell_value(snap, overlay2, "General", "C20") == 4.50


class _FakeQueryJob:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def result(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeBQClient:
    def __init__(self) -> None:
        self.queries: list[tuple[str, Any]] = []
        self.inserted_rows: list[tuple[str, list[dict[str, Any]]]] = []

    def query(self, sql: str, job_config: Any = None) -> _FakeQueryJob:
        self.queries.append((sql, job_config))
        if "dt_workbook_versions" in sql:
            return _FakeQueryJob(
                [
                    {
                        "workbook_id": "brazil_power_v13",
                        "version_id": "v13_baseline",
                        "version_label": "Brazil v13",
                        "named_ranges_json": "[]",
                        "solver_parameters_json": json.dumps({"_01_CF": {"capex_brl_kw": 3814.35}}),
                    }
                ]
            )
        if "dt_worksheets" in sql:
            return _FakeQueryJob(
                [
                    {
                        "sheet_index": 0,
                        "sheet_name": "General",
                        "visibility": "visible",
                        "tab_color_rgb": None,
                        "merged_ranges_json": "[]",
                        "col_widths_json": "{}",
                        "row_heights_json": "{}",
                        "freeze_panes_coord": None,
                    }
                ]
            )
        if "dt_styles" in sql:
            return _FakeQueryJob(
                [
                    {
                        "style_id": 0,
                        "number_format": "General",
                        "font_json": "{}",
                        "fill_json": "{}",
                        "border_json": "{}",
                        "alignment_json": "{}",
                    }
                ]
            )
        if "dt_cells" in sql:
            return _FakeQueryJob(
                [
                    {
                        "sheet_name": "General",
                        "cell_coord": "C20",
                        "row_num": 20,
                        "col_num": 3,
                        "data_type": "n",
                        "numeric_value": 4.50,
                        "string_value": None,
                        "raw_formula": None,
                        "style_id": 0,
                        "semantic_role": "INPUT",
                    }
                ]
            )
        return _FakeQueryJob([])

    def insert_rows_json(self, table: str, json_rows: list[dict[str, Any]]) -> list[Any]:
        self.inserted_rows.append((table, json_rows))
        return []


def test_bigquery_store_enforces_parameterized_queries_and_bytes_cap() -> None:
    fake_bq = _FakeBQClient()
    settings = TwinSettings(max_bytes_billed=50 * 1024 * 1024)
    store = BigQueryDigitalTwinStore(settings=settings, bq_client=fake_bq)

    snap = store.get_baseline_snapshot("v13_baseline")
    assert snap.get_cell("General", "C20") is not None
    assert snap.solver_parameters["_01_CF"]["capex_brl_kw"] == 3814.35

    for sql, job_cfg in fake_bq.queries:
        assert "@version_id" in sql
        assert job_cfg.maximum_bytes_billed == 50 * 1024 * 1024

    store.append_session_deltas(
        "sess_cloud_1",
        [
            CellDelta(
                sheet_name="General",
                cell_coord="C20",
                row_num=20,
                col_num=3,
                delta_kind="USER_OVERRIDE",
                numeric_value=7.25,
                source_tool="update_session_assumptions",
            )
        ],
    )
    # Write-through cache provides immediate read-after-write consistency
    overlay = store.get_session_overlay("sess_cloud_1")
    assert resolve_effective_cell_value(snap, overlay, "General", "C20") == 7.25
    assert len(fake_bq.inserted_rows) == 1
