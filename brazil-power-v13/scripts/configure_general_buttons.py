"""Configures button row heights, cell formatting, labels, and freeze settings on General!B42:N52."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

import google.auth
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build

from src.cli.extract_baseline_fixtures import col_letter_to_index, split_coord
from src.core.config import get_settings

# Complete 31-button canonical specification on General!B42:N52 (after Row 41 spacer insertion)
BUTTON_DECK_SPECS: list[dict[str, Any]] = [
    # Master Forecast LCOE button (Row 43, Col B)
    {
        "coord": "B43",
        "label": "Forecast LCOE",
        "macro": "lcoe_exec",
        "group": "master",
        "bg": {"red": 0.106, "green": 0.212, "blue": 0.365},
    },
    # 12 Tornado IRR buttons (Row 42, Cols C..N)
    *[
        {
            "coord": f"{col}42",
            "label": f"Tornado {i}",
            "macro": f"calcule_tir{i}",
            "group": "tornado",
            "bg": {"red": 0.122, "green": 0.306, "blue": 0.475},
        }
        for i, col in enumerate(
            ["C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"], start=1
        )
    ],
    # 12 Fuel / CVU Sweep buttons (Row 45, Cols C..N)
    *[
        {
            "coord": f"{col}45",
            "label": f"Fuel/CVU{i}",
            "macro": f"calculo_cvu{i}",
            "group": "cvu",
            "bg": {"red": 0.180, "green": 0.420, "blue": 0.557},
        }
        for i, col in enumerate(
            ["C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"], start=1
        )
    ],
    # 6 Specialized 1D/2D Sensitivity & BI LCOE buttons (Rows 48 & 52)
    {
        "coord": "D48",
        "label": "BI LCOE",
        "macro": "calculo_cvu2bi",
        "group": "bi",
        "bg": {"red": 0.231, "green": 0.286, "blue": 0.565},
    },
    {
        "coord": "F48",
        "label": "BI LCOE",
        "macro": "calculo_cvu4bi",
        "group": "bi",
        "bg": {"red": 0.231, "green": 0.286, "blue": 0.565},
    },
    {
        "coord": "G48",
        "label": "Capex vs IRR",
        "macro": "calculo_capexvscf",
        "group": "sens1d",
        "bg": {"red": 0.114, "green": 0.435, "blue": 0.447},
    },
    {
        "coord": "H48",
        "label": "Price vs IRR",
        "macro": "calculo_priceirr",
        "group": "sens1d",
        "bg": {"red": 0.114, "green": 0.435, "blue": 0.447},
    },
    {
        "coord": "G52",
        "label": "BI LCOE",
        "macro": "calculo_capexvscfbi",
        "group": "bi",
        "bg": {"red": 0.231, "green": 0.286, "blue": 0.565},
    },
    {
        "coord": "H52",
        "label": "BI LCOE",
        "macro": "calculo_priceirr_bi",
        "group": "bi",
        "bg": {"red": 0.231, "green": 0.286, "blue": 0.565},
    },
]


def _get_sheets_service(project_id: str) -> Any:
    token_proc = subprocess.run(
        [
            "gcloud",
            "auth",
            "print-access-token",
            "admin@ferozmulla.altostrat.com",
            "--scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if token_proc.returncode == 0 and token_proc.stdout.strip():
        creds: Any = OAuthCredentials(
            token=token_proc.stdout.strip(),
            quota_project_id=project_id,
        )
    else:
        creds, _ = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets",
            ]
        )
        if hasattr(creds, "with_quota_project"):
            creds = creds.with_quota_project(project_id)
    return build("sheets", "v4", credentials=creds)


def configure_live_general_buttons(
    spreadsheet_id: str,
    project_id: str,
    freeze_rows: int = 5,
    freeze_cols: int = 2,
) -> dict[str, Any]:
    """Apply button row heights, cell labels/styles, freeze panes, and row grouping on General."""
    sheets_service = _get_sheets_service(project_id)
    meta = (
        sheets_service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, includeGridData=False)
        .execute()
    )

    general_sheet_id: int | None = None
    existing_row_groups: list[dict[str, Any]] = []
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == "General":
            general_sheet_id = int(props["sheetId"])
            existing_row_groups = s.get("rowGroups", [])
            break

    if general_sheet_id is None:
        raise ValueError("Worksheet 'General' not found in spreadsheet.")

    requests: list[dict[str, Any]] = []

    # 1. Freeze header rows (1..5) and parameter columns (A..B)
    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": general_sheet_id,
                    "gridProperties": {
                        "frozenRowCount": freeze_rows,
                        "frozenColumnCount": freeze_cols,
                    },
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        }
    )

    # 2. Set spacer rows (41, 44, 46, 47, 49, 50, 51) to 18px and button rows (42, 43, 45, 48, 52) to 36px
    for r_spacer in (41, 44, 46, 47, 49, 50, 51):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": general_sheet_id,
                        "dimension": "ROWS",
                        "startIndex": r_spacer - 1,
                        "endIndex": r_spacer,
                    },
                    "properties": {"pixelSize": 18},
                    "fields": "pixelSize",
                }
            }
        )

    for r_btn in (42, 43, 45, 48, 52):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": general_sheet_id,
                        "dimension": "ROWS",
                        "startIndex": r_btn - 1,
                        "endIndex": r_btn,
                    },
                    "properties": {"pixelSize": 36},
                    "fields": "pixelSize",
                }
            }
        )

    # 3. Ensure collapsible Row Group on Rows 6..40 (0-based 5..40)
    has_group = any(
        rg.get("range", {}).get("startIndex") == 5 for rg in existing_row_groups
    )
    if not has_group:
        requests.append(
            {
                "addDimensionGroup": {
                    "range": {
                        "sheetId": general_sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 5,
                        "endIndex": 40,
                    }
                }
            }
        )

    # 4. Reset B41:N52 first so spacer rows (41, 44, 46, 47, 49, 50, 51) have no leftover formatting
    border_none = {"style": "NONE"}
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": general_sheet_id,
                    "startRowIndex": 40,
                    "endRowIndex": 52,
                    "startColumnIndex": 1,
                    "endColumnIndex": 14,
                },
                "cell": {
                    "userEnteredValue": {"stringValue": ""},
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "borders": {
                            "top": border_none,
                            "bottom": border_none,
                            "left": border_none,
                            "right": border_none,
                        },
                    },
                },
                "fields": "userEnteredValue,userEnteredFormat(backgroundColor,borders)",
            }
        }
    )

    # 5. Format all 31 active button slot cells on General!B42:N52
    border_side = {
        "style": "SOLID_MEDIUM",
        "color": {"red": 0.25, "green": 0.35, "blue": 0.48},
    }
    fg_white = {"red": 1.0, "green": 1.0, "blue": 1.0}

    for spec in BUTTON_DECK_SPECS:
        col_str, row_1 = split_coord(spec["coord"])
        col_1 = col_letter_to_index(col_str)
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": general_sheet_id,
                        "startRowIndex": row_1 - 1,
                        "endRowIndex": row_1,
                        "startColumnIndex": col_1 - 1,
                        "endColumnIndex": col_1,
                    },
                    "cell": {
                        "userEnteredValue": {"stringValue": spec["label"]},
                        "userEnteredFormat": {
                            "backgroundColor": spec["bg"],
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "fontFamily": "Lexend",
                                "fontSize": 9,
                                "bold": True,
                                "foregroundColor": fg_white,
                            },
                            "borders": {
                                "top": border_side,
                                "bottom": border_side,
                                "left": border_side,
                                "right": border_side,
                            },
                        },
                    },
                    "fields": "userEnteredValue,userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,borders)",
                }
            }
        )

    # Add row category guide labels in Column B for rows 42, 45, 48, 52
    row_guides = [
        (42, "Tornado IRR Suite (1..12) ->"),
        (45, "Fuel / CVU Sweeps (1..12) ->"),
        (48, "1D / 2D Sensitivity Suite ->"),
        (52, "2D Bivariate LCOE Suite ->"),
    ]
    for r_num, guide_text in row_guides:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": general_sheet_id,
                        "startRowIndex": r_num - 1,
                        "endRowIndex": r_num,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredValue": {"stringValue": guide_text},
                        "userEnteredFormat": {
                            "horizontalAlignment": "RIGHT",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "fontFamily": "Lexend",
                                "fontSize": 9,
                                "bold": True,
                                "italic": True,
                                "foregroundColor": {"red": 0.22, "green": 0.29, "blue": 0.39},
                            },
                        },
                    },
                    "fields": "userEnteredValue,userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat)",
                }
            }
        )

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()

    return {
        "spreadsheet_id": spreadsheet_id,
        "general_sheet_id": general_sheet_id,
        "frozen_rows": freeze_rows,
        "frozen_columns": freeze_cols,
        "button_rows": [42, 43, 45, 48, 52],
        "configured_button_cells": len(BUTTON_DECK_SPECS),
    }


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Configure the 31 button slots, row heights, and freeze settings on General!B42:N52."
    )
    parser.add_argument(
        "--spreadsheet-id",
        default="1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI",
    )
    parser.add_argument(
        "--freeze-rows",
        type=int,
        default=5,
        help="Number of top rows to freeze on General",
    )
    parser.add_argument(
        "--freeze-cols",
        type=int,
        default=2,
        help="Number of left columns (A:B) to freeze on General",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Apply changes to the live Google Sheet via the Google Sheets v4 API",
    )
    args = parser.parse_args()

    if args.live:
        res = configure_live_general_buttons(
            spreadsheet_id=args.spreadsheet_id,
            project_id=settings.gcp_project_id,
            freeze_rows=args.freeze_rows,
            freeze_cols=args.freeze_cols,
        )
        print(json.dumps(res, indent=2))
        return 0

    print(
        json.dumps(
            {
                "button_specs_count": len(BUTTON_DECK_SPECS),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
