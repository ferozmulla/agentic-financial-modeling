from pathlib import Path
from typing import Any
import openpyxl
from brazil_power_agent.session_store import BrazilPowerSessionManager
from brazil_power_agent.workbook_exporter import (
    EXPECTED_22_TABS,
    GOLDEN_GOOGLE_SHEET_ID,
    export_full_22tab_workbook,
)


def test_export_22tab_xlsx_preserves_all_sheets_and_applies_session_edits(tmp_path: Path) -> None:
    mgr = BrazilPowerSessionManager(session_path=tmp_path / "session.json")
    mgr.update_assumptions(overrides={"General!C20": 6.50, "General!H14": 2.0})
    mgr.run_tornado(technology_code="_06_CF")
    mgr.run_lcoe_horizon()

    res = export_full_22tab_workbook(
        session_mgr=mgr,
        export_format="xlsx",
        output_dir=tmp_path,
        filename="Brazil_TT_v13_Scenario_Test.xlsx",
    )
    xlsx_path = Path(res["xlsx_path"])
    assert xlsx_path.exists()

    wb = openpyxl.load_workbook(xlsx_path, data_only=False)
    assert len(wb.sheetnames) == 22
    assert tuple(wb.sheetnames) == EXPECTED_22_TABS
    assert wb["General"]["C20"].value == 6.50
    assert wb["General"]["H14"].value == 2.0
    assert wb["Output_3"]["B9"].value is not None
    assert wb["Output_3"]["B3"].value is not None
    assert wb["_06_CF"]["E6"].value is not None
    assert wb["_06_CF"]["G12"].value is not None

    # Verify formulas, styles, number formats, column widths, and merged cells remain intact
    assert isinstance(wb["_01_CF"]["B18"].value, str) and wb["_01_CF"]["B18"].value.startswith("=")
    assert wb["General"]["C20"].font is not None
    assert len(wb["General"].merged_cells.ranges) > 0
    wb.close()


class _FakeExecute:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def execute(self) -> dict[str, Any]:
        return self._payload


class _FakeDriveFiles:
    def __init__(self) -> None:
        self.copy_calls: list[dict[str, Any]] = []

    def copy(self, **kwargs: Any) -> _FakeExecute:
        self.copy_calls.append(kwargs)
        return _FakeExecute({"id": "cloned-22tab-sheet-id-999", "name": kwargs.get("body", {}).get("name")})


class _FakeDriveService:
    def __init__(self) -> None:
        self.files_resource = _FakeDriveFiles()

    def files(self) -> _FakeDriveFiles:
        return self.files_resource


class _FakeSheetsValues:
    def __init__(self) -> None:
        self.batch_calls: list[dict[str, Any]] = []

    def batchUpdate(self, **kwargs: Any) -> _FakeExecute:
        self.batch_calls.append(kwargs)
        return _FakeExecute({"totalUpdatedCells": len(kwargs.get("body", {}).get("data", []))})


class _FakeSpreadsheets:
    def __init__(self) -> None:
        self.values_resource = _FakeSheetsValues()

    def values(self) -> _FakeSheetsValues:
        return self.values_resource


class _FakeSheetsService:
    def __init__(self) -> None:
        self.spreadsheets_resource = _FakeSpreadsheets()

    def spreadsheets(self) -> _FakeSpreadsheets:
        return self.spreadsheets_resource


def test_export_google_sheets_and_both_with_bqml_and_cvu_sweep(tmp_path: Path) -> None:
    mgr = BrazilPowerSessionManager(session_path=tmp_path / "session_gs.json")
    mgr.update_assumptions(overrides={"General!C20": 7.25, "CVU_GF!C5": 412.5})
    mgr.run_bqml_refresh(curve_types=["CAPEX", "FUEL", "CF"])
    mgr.run_cvu_sweep(technology_code="_01_CF")
    # Re-run tornado twice to verify deduplication of cell_range_updates
    mgr.run_tornado(technology_code="_01_CF")
    mgr.run_tornado(technology_code="_01_CF")
    tornado_ranges = [
        r for r in mgr.cell_range_updates if r["sheet"] == "_01_CF" and r["range"] == "E6:G12"
    ]
    assert len(tornado_ranges) == 1

    fake_drive = _FakeDriveService()
    fake_sheets = _FakeSheetsService()

    res = export_full_22tab_workbook(
        session_mgr=mgr,
        export_format="both",
        output_dir=tmp_path,
        filename="Brazil_TT_v13_Combined_Test",
        sheet_title="Brazil v13 Cloned Scenario",
        drive_service=fake_drive,
        sheets_service=fake_sheets,
    )

    assert Path(res["xlsx_path"]).exists()
    assert res["spreadsheet_id"] == "cloned-22tab-sheet-id-999"
    assert res["golden_sheet_id"] == GOLDEN_GOOGLE_SHEET_ID
    assert "docs.google.com/spreadsheets/d/cloned-22tab-sheet-id-999" in res["spreadsheet_url"]

    assert len(fake_drive.files_resource.copy_calls) == 1
    copy_call = fake_drive.files_resource.copy_calls[0]
    assert copy_call["fileId"] == GOLDEN_GOOGLE_SHEET_ID
    assert copy_call["body"]["name"] == "Brazil v13 Cloned Scenario"

    assert len(fake_sheets.spreadsheets_resource.values_resource.batch_calls) == 1
    batch_call = fake_sheets.spreadsheets_resource.values_resource.batch_calls[0]
    assert batch_call["spreadsheetId"] == "cloned-22tab-sheet-id-999"
    assert batch_call["body"]["valueInputOption"] == "USER_ENTERED"
    ranges_sent = {entry["range"]: entry["values"][0][0] for entry in batch_call["body"]["data"]}
    assert ranges_sent["General!C20"] == 7.25
    assert ranges_sent["CVU_GF!C5"] == 412.5
    assert "'LT Capex'!B8" in ranges_sent
    assert "_01_CF!C70" in ranges_sent
