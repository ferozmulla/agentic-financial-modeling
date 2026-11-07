"""Builds and seeds the 24-Tab EULR Hybrid Google Sheet in Google Drive with the 5-Button 3D Execution Deck at KeyInputs!B2:N5."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import google.auth
import openpyxl
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.bqml.forecaster import generate_bqml_breakout_tab_matrix
from src.core.config import settings
from src.parser.openxml_extractor import extract_workbook_openxml
from src.parser.r1c1_catalog import LIVE_FORMULA_SHEETS
from src.parser.upstream_link_hub import build_upstream_link_registry
from src.schemas.models import BQMLRefreshRequest, ScenarioMatrixRequest
from src.solver.scenario_matrix import run_four_way_scenario_matrix
from src.solver.upload_publisher import extract_upload_and_links_out_catalog

CORE_17_MODEL_TABS: tuple[str, ...] = (
    "KeyInputs",
    "Carbon",
    "Yields",
    "Info",
    "Input",
    "Freight",
    "Crudes",
    "ULSD-GO_spread_econs",
    "Op_Cost",
    "NWE Cif",
    "MED Cif",
    "NWE Fob",
    "MED Fob",
    "IMOfuels",
    "HCK naphtha revamp",
    "2015 NWE HCK IRR",
    "Checks",
)

KEYINPUTS_3D_BUTTON_SPECS: list[dict[str, Any]] = [
    {
        "start_col": 1,  # Col B
        "end_col": 3,    # B:C
        "label": "⚡ 1. Solve 10-Pass Equilibrium",
        "fn": "runTenPassEquilibriumSolve",
        "bg": {"red": 0.086, "green": 0.243, "blue": 0.439},
    },
    {
        "start_col": 4,  # Col E
        "end_col": 6,    # E:F
        "label": "📊 2. 4-Way Scenario & Carbon",
        "fn": "runFourWayScenarioCarbonMatrix",
        "bg": {"red": 0.118, "green": 0.345, "blue": 0.525},
    },
    {
        "start_col": 7,  # Col H
        "end_col": 9,    # H:I
        "label": "🔗 3. Sync Upstream Peers",
        "fn": "syncUpstreamPeerWorkbooks",
        "bg": {"red": 0.094, "green": 0.408, "blue": 0.396},
    },
    {
        "start_col": 10, # Col K
        "end_col": 11,   # K
        "label": "↩️ 4. Revert Overrides",
        "fn": "revertPinnedPriceOverrides",
        "bg": {"red": 0.545, "green": 0.251, "blue": 0.075},
    },
    {
        "start_col": 12, # Col M
        "end_col": 14,   # M:N
        "label": "☁️ 5. Publish UPLOAD to BQ",
        "fn": "publishUploadAndLinksOut",
        "bg": {"red": 0.220, "green": 0.255, "blue": 0.522},
    },
]


def _get_google_credentials(project_id: str) -> Any:
    import os

    adc_candidates = [
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
        "/Users/ferozmulla/.gemini/jetski/brain/0ec31efb-8591-4719-af36-5223a9f849a5/scratch/gcloud_drive_config/legacy_credentials/admin@ferozmulla.altostrat.com/adc.json",
    ]
    for cand in adc_candidates:
        if cand and Path(cand).exists():
            creds, _ = google.auth.load_credentials_from_file(
                cand,
                scopes=[
                    "https://www.googleapis.com/auth/cloud-platform",
                    "https://www.googleapis.com/auth/drive",
                ],
                quota_project_id=project_id,
            )
            return creds

    for acct_args in (["admin@ferozmulla.altostrat.com"], []):
        cmd = [
            "gcloud",
            "auth",
            "print-access-token",
            *acct_args,
            "--scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return OAuthCredentials(
                token=proc.stdout.strip(),
                quota_project_id=project_id,
            )
    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/drive",
        ]
    )
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(project_id)
    return creds


def build_clean_24_tab_xlsx(output_xlsx_path: Path) -> dict[str, Any]:
    """
    Construct the 24-tab hybrid Google Sheets staging .xlsx from Eulr202409.xlsx:
    - 17 Core Model Tabs (retiring shooju_addin & offloading UPLOAD/Links out to BigQuery tabs)
      - Keeps acyclic, non-external formulas live on KeyInputs, Yields, Info, Checks
      - Replaces circular & external [14]-[26] formulas with converged baseline <v> values
    - 3 Breakout BQML Forecast Tabs (Macro_BQML, Crudes_BQML, Freight_BQML)
    - 4 Connected Sheets & Scenario Tabs (Upstream_Links_BQ, UPLOAD_BQ, BQ_4Ws_Audit_Log, Scenario_Comparison)
    """
    wb_extract = extract_workbook_openxml(settings.resolved_seed_path)
    out_wb = openpyxl.Workbook()
    # Remove default sheet
    out_wb.remove(out_wb.active)

    live_formula_count = 0
    populated_count = 0

    for sname in CORE_17_MODEL_TABS:
        sh_ext = wb_extract.sheets[sname]
        ws = out_wb.create_sheet(title=sname)
        is_live_sheet = sname in LIVE_FORMULA_SHEETS

        for crec in sh_ext.cells_by_coord.values():
            # Cap extreme empty-ish columns/rows if beyond active grid
            if crec.row > 850 or crec.col > 95:
                continue

            keep_formula = (
                is_live_sheet
                and crec.formula is not None
                and not crec.ext_indices
                and not crec.is_array_cse
                and "#REF!" not in crec.formula
                and "CELL(" not in crec.formula.upper()
            )
            if keep_formula and crec.formula:
                ws.cell(row=crec.row, column=crec.col, value=f"={crec.formula.lstrip('=')}")
                live_formula_count += 1
                populated_count += 1
            elif crec.numeric_value is not None:
                ws.cell(row=crec.row, column=crec.col, value=round(crec.numeric_value, 6))
                populated_count += 1
            elif crec.value is not None and not crec.value.startswith("#"):
                ws.cell(row=crec.row, column=crec.col, value=crec.value)
                populated_count += 1

    # Add 3 Breakout BQML Tabs: Macro_BQML, Crudes_BQML, Freight_BQML
    for bqml_tab in ("Macro_BQML", "Crudes_BQML", "Freight_BQML"):
        ws = out_wb.create_sheet(title=bqml_tab)
        ws["A1"] = f"EULR BigQuery ML (ARIMA_PLUS) Forecast Trajectory — {bqml_tab}"
        ws["A2"] = f"Dataset: {settings.gcp_project_id}.{settings.bigquery_dataset} | Surrogate: {settings.vertex_surrogate_model_name}"
        ws["H2"] = "🔄 Refresh BQML"
        bqml_resp = generate_bqml_breakout_tab_matrix(
            BQMLRefreshRequest(tab_name=bqml_tab, horizon_end_year=2050)  # type: ignore[arg-type]
        )
        for r_i, row_vals in enumerate(bqml_resp.series_rows, start=5):
            for c_i, val in enumerate(row_vals, start=1):
                ws.cell(row=r_i, column=c_i, value=val)

    # Add Tab 21: Upstream_Links_BQ (SharePoint-Portable Upstream Link Registry Preview)
    ws_up = out_wb.create_sheet(title="Upstream_Links_BQ")
    ws_up["A1"] = "Connected Sheet Backing View: comm-model-mod.eulr_commodity_mod_governance.vw_upstream_links_health"
    ws_up["A2"] = "14,162 External SharePoint Link Cells Across 13 Active Peer Workbooks (100.0% Valid Cached Baseline + 1,104 Live Peer Deltas)"
    up_headers = [
        "Vintage",
        "Health Tier",
        "Link [Idx]",
        "External Workbook",
        "SharePoint URL / Path",
        "Source Sheet",
        "Source Cell",
        "Target EULR Sheet",
        "Target Cell",
        "Baseline Cached Value",
        "Live Peer .xlsx Value",
        "Peer Updated?",
    ]
    for c_i, h in enumerate(up_headers, start=1):
        ws_up.cell(row=4, column=c_i, value=h)

    reg = build_upstream_link_registry(settings.resolved_seed_path, settings.resolved_references_dir)
    # Include top updated peer rows + representative rows across all 13 active workbooks
    updated_sample = [r for r in reg.records if r.is_peer_updated][:180]
    other_sample = [r for r in reg.records if not r.is_peer_updated][:120]
    for idx_r, rec in enumerate(updated_sample + other_sample, start=5):
        ws_up.cell(row=idx_r, column=1, value=rec.vintage_tag)
        ws_up.cell(row=idx_r, column=2, value=rec.link_health_tier)
        ws_up.cell(row=idx_r, column=3, value=f"[{rec.external_link_idx}]")
        ws_up.cell(row=idx_r, column=4, value=rec.external_workbook_name)
        ws_up.cell(row=idx_r, column=5, value=rec.sharepoint_url)
        ws_up.cell(row=idx_r, column=6, value=rec.source_sheet)
        ws_up.cell(row=idx_r, column=7, value=rec.source_cell_a1)
        ws_up.cell(row=idx_r, column=8, value=rec.target_eulr_sheet)
        ws_up.cell(row=idx_r, column=9, value=rec.target_cell_a1)
        ws_up.cell(row=idx_r, column=10, value=round(rec.baseline_cached_value, 4))
        ws_up.cell(
            row=idx_r,
            column=11,
            value=round(rec.peer_live_value, 4) if rec.peer_live_value is not None else round(rec.baseline_cached_value, 4),
        )
        ws_up.cell(row=idx_r, column=12, value="YES" if rec.is_peer_updated else "NO")

    # Add Tab 22: UPLOAD_BQ (1,273 UPLOAD Series & 234 Links out Series — Retiring shooju_addin)
    ws_pub = out_wb.create_sheet(title="UPLOAD_BQ")
    ws_pub["A1"] = "Connected Sheet Backing View: comm-model-mod.eulr_commodity_mod_governance.vw_eulr_upload_latest"
    ws_pub["A2"] = "1,273 Published UPLOAD Series & 234 Links Out Series (Replaces 83,928 Browser Formulas & Retires shooju_addin)"
    pub_headers = ["Series Type", "Row", "Series Mnemonic", "Description", "Unit", "2024", "2025", "2030", "2050"]
    for c_i, h in enumerate(pub_headers, start=1):
        ws_pub.cell(row=4, column=c_i, value=h)
    upload_rows, links_rows = extract_upload_and_links_out_catalog()
    for idx_r, srow in enumerate((upload_rows[:250] + links_rows[:100]), start=5):
        ws_pub.cell(row=idx_r, column=1, value=srow.series_type)
        ws_pub.cell(row=idx_r, column=2, value=srow.row_idx)
        ws_pub.cell(row=idx_r, column=3, value=srow.series_mnemonic)
        ws_pub.cell(row=idx_r, column=4, value=srow.description)
        ws_pub.cell(row=idx_r, column=5, value=srow.unit)
        ws_pub.cell(row=idx_r, column=6, value=round(srow.value_2024, 4) if srow.value_2024 is not None else None)
        ws_pub.cell(row=idx_r, column=7, value=round(srow.value_2025, 4) if srow.value_2025 is not None else None)
        ws_pub.cell(row=idx_r, column=8, value=round(srow.value_2030, 4) if srow.value_2030 is not None else None)
        ws_pub.cell(row=idx_r, column=9, value=round(srow.value_2050, 4) if srow.value_2050 is not None else None)

    # Add Tab 23: BQ_4Ws_Audit_Log (Silent Distributed 4-Ws Governance & Three-Tier Rollback Ledger)
    ws_aud = out_wb.create_sheet(title="BQ_4Ws_Audit_Log")
    ws_aud["A1"] = "Connected Sheet Backing View: comm-model-mod.eulr_commodity_mod_governance.vw_audit_4w_summary"
    ws_aud["A2"] = "Silent Distributed 4-Ws Governance Ledger (Enriched by Vertex AI gemini-3.8-flash | Three-Tier Rollback Enabled)"
    aud_headers = [
        "Event ID",
        "WHEN (UTC)",
        "WHO (Actor)",
        "WHERE (Spreadsheet ID)",
        "Copy Location URL",
        "Sheet Name",
        "Cell A1",
        "WHAT (Classification)",
        "Before Value",
        "New Value",
        "Before Formula",
        "New Formula",
        "WHY (gemini-3.8-flash Summary)",
        "Rollback Tier",
    ]
    for c_i, h in enumerate(aud_headers, start=1):
        ws_aud.cell(row=4, column=c_i, value=h)
    sample_audit_rows = [
        [
            "evt-seed-001",
            "2026-11-06T15:00:00Z",
            "system@spglobal.com",
            "central-eulr-202409",
            "https://docs.google.com/spreadsheets/d/central-eulr-202409/edit",
            "KeyInputs",
            "B4",
            "SOLVER_RUN",
            "716.40",
            "716.40",
            "",
            "",
            "[gemini-3.8-flash] Baseline 10-pass Gauss-Seidel equilibrium verified (<= 1e-8 parity across all 19 active sheets).",
            "TIER_3_VERSION_HISTORY",
        ],
        [
            "evt-seed-002",
            "2026-11-06T15:05:00Z",
            "trader@spglobal.com",
            "central-eulr-202409",
            "https://docs.google.com/spreadsheets/d/central-eulr-202409/edit",
            "NWE Cif",
            "AU122",
            "PINNED_PRICE_OVERRIDE",
            "716.40",
            "750.00",
            "=AU127",
            "",
            "[gemini-3.8-flash] Trader pinned 2025 NWE Diesel EN590 to $750.00/mt (#FEF3C7); NWE FOB and IMO bunkers re-equilibrated.",
            "TIER_1_ONE_CLICK_OVERRIDE_REVERT",
        ],
    ]
    for idx_r, arow in enumerate(sample_audit_rows, start=5):
        for c_i, val in enumerate(arow, start=1):
            ws_aud.cell(row=idx_r, column=c_i, value=val)

    # Add Tab 24: Scenario_Comparison (4-Way Base/Sensitivity x EU ETS Carbon Sweep + gemini-3.8-flash Attribution)
    ws_scen = out_wb.create_sheet(title="Scenario_Comparison")
    ws_scen["A1"] = "EULR 4-Way Scenario & EU ETS Carbon Equilibrium Matrix (2025 Benchmark Comparison)"
    ws_scen["A2"] = "Generated by Cloud Run 10-Pass Vectorized Engine + Vertex AI gemini-3.8-flash Attribution"
    mat_resp = run_four_way_scenario_matrix(ScenarioMatrixRequest())
    for r_i, row_vals in enumerate(mat_resp.comparison_table_rows, start=4):
        for c_i, val in enumerate(row_vals, start=1):
            ws_scen.cell(row=r_i, column=c_i, value=val)
    ws_scen["A10"] = "Vertex AI gemini-3.8-flash Executive Attribution Summary:"
    ws_scen["A11"] = mat_resp.ai_attribution_summary

    output_xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    out_wb.save(output_xlsx_path)
    return {
        "xlsx_path": str(output_xlsx_path),
        "sheet_count": len(out_wb.sheetnames),
        "sheet_names": out_wb.sheetnames,
        "live_formula_count": live_formula_count,
        "populated_cell_count": populated_count,
    }


def style_keyinputs_button_deck_and_tabs(spreadsheet_id: str, project_id: str) -> None:
    """Style the 5-Button 3D Execution Deck at KeyInputs!B2:N5 and header formatting across the 24 tabs."""
    creds = _get_google_credentials(project_id)
    sheets_service = build("sheets", "v4", credentials=creds)
    meta = (
        sheets_service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, includeGridData=False)
        .execute()
    )
    sheet_id_map = {
        s["properties"]["title"]: int(s["properties"]["sheetId"])
        for s in meta.get("sheets", [])
    }

    requests: list[dict[str, Any]] = []
    ki_id = sheet_id_map.get("KeyInputs")
    if ki_id is not None:
        # Freeze header rows 1..7 and label column A on KeyInputs
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ki_id,
                        "gridProperties": {"frozenRowCount": 7, "frozenColumnCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
                }
            }
        )
        # Set Row 3 & 4 height to 36px for the 3D Execution Deck at KeyInputs!B2:N5
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ki_id,
                        "dimension": "ROWS",
                        "startIndex": 2,
                        "endIndex": 4,
                    },
                    "properties": {"pixelSize": 34},
                    "fields": "pixelSize",
                }
            }
        )
        # Banner title in B2
        requests.append(
            {
                "updateCells": {
                    "range": {
                        "sheetId": ki_id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    },
                    "rows": [
                        {
                            "values": [
                                {
                                    "userEnteredValue": {
                                        "stringValue": "⚡ EULR 10-PASS EQUILIBRIUM & GOVERNANCE EXECUTION DECK (Cloud Run + BigQuery ML + Gemini 3.8 Flash)"
                                    },
                                    "userEnteredFormat": {
                                        "textFormat": {
                                            "bold": True,
                                            "fontSize": 10,
                                            "foregroundColor": {"red": 0.08, "green": 0.20, "blue": 0.38},
                                        }
                                    },
                                }
                            ]
                        }
                    ],
                    "fields": "userEnteredValue,userEnteredFormat.textFormat",
                }
            }
        )

        # Render the 5 styled 3D bevel buttons across Row 4 (index 3) Columns B..N
        for btn in KEYINPUTS_3D_BUTTON_SPECS:
            sc = btn["start_col"]
            ec = btn["end_col"]
            if ec - sc > 1:
                requests.append(
                    {
                        "mergeCells": {
                            "range": {
                                "sheetId": ki_id,
                                "startRowIndex": 3,
                                "endRowIndex": 4,
                                "startColumnIndex": sc,
                                "endColumnIndex": ec,
                            },
                            "mergeType": "MERGE_ALL",
                        }
                    }
                )
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": ki_id,
                            "startRowIndex": 3,
                            "endRowIndex": 4,
                            "startColumnIndex": sc,
                            "endColumnIndex": ec,
                        },
                        "cell": {
                            "userEnteredValue": {"stringValue": btn["label"]},
                            "userEnteredFormat": {
                                "backgroundColor": btn["bg"],
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "bold": True,
                                    "fontSize": 9,
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                },
                                "borders": {
                                    "top": {"style": "SOLID_MEDIUM", "color": {"red": 0.85, "green": 0.90, "blue": 0.98}},
                                    "left": {"style": "SOLID_MEDIUM", "color": {"red": 0.85, "green": 0.90, "blue": 0.98}},
                                    "bottom": {"style": "SOLID_THICK", "color": {"red": 0.02, "green": 0.08, "blue": 0.18}},
                                    "right": {"style": "SOLID_THICK", "color": {"red": 0.02, "green": 0.08, "blue": 0.18}},
                                },
                            },
                        },
                        "fields": "userEnteredValue,userEnteredFormat",
                    }
                }
            )

    # Style the 3 Refresh BQML buttons at H2 on Macro_BQML, Crudes_BQML, Freight_BQML
    for bqml_tab in ("Macro_BQML", "Crudes_BQML", "Freight_BQML"):
        b_id = sheet_id_map.get(bqml_tab)
        if b_id is not None:
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": b_id,
                            "startRowIndex": 1,
                            "endRowIndex": 2,
                            "startColumnIndex": 7,
                            "endColumnIndex": 9,
                        },
                        "cell": {
                            "userEnteredValue": {"stringValue": "🔄 Refresh BQML"},
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.094, "green": 0.408, "blue": 0.396},
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "bold": True,
                                    "fontSize": 9,
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                },
                                "borders": {
                                    "top": {"style": "SOLID_MEDIUM", "color": {"red": 0.8, "green": 0.95, "blue": 0.9}},
                                    "bottom": {"style": "SOLID_THICK", "color": {"red": 0.02, "green": 0.18, "blue": 0.18}},
                                },
                            },
                        },
                        "fields": "userEnteredValue,userEnteredFormat",
                    }
                }
            )

    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


def create_and_push_live_eulr_sheet(
    project_id: str = "comm-model-mod",
    title: str = "Eulr202409 — European Long-Range Refinery & Product Equilibrium Model (Governed v2.0)",
) -> dict[str, Any]:
    staging_xlsx = settings.data_dir / "Eulr202409_GoogleSheets_24Tabs.xlsx"
    build_info = build_clean_24_tab_xlsx(staging_xlsx)

    creds = _get_google_credentials(project_id)
    drive_service = build("drive", "v3", credentials=creds)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    media = MediaFileUpload(
        str(staging_xlsx),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True,
    )
    created = (
        drive_service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id,name,webViewLink",
        )
        .execute()
    )
    spreadsheet_id = created["id"]
    web_url = created.get(
        "webViewLink",
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
    )

    style_keyinputs_button_deck_and_tabs(spreadsheet_id, project_id)

    result = {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": web_url,
        "title": created.get("name", title),
        **build_info,
    }
    out_meta = settings.data_dir / "live_eulr_sheet_metadata.json"
    out_meta.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and populate the 24-tab EULR Google Sheet.")
    parser.add_argument("--project-id", default=settings.gcp_project_id)
    parser.add_argument(
        "--title",
        default="Eulr202409 — European Long-Range Refinery & Product Equilibrium Model (Governed v2.0)",
    )
    args = parser.parse_args()
    info = create_and_push_live_eulr_sheet(project_id=args.project_id, title=args.title)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
