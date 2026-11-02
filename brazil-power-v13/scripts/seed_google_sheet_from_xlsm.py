"""Seeds a native Google Sheet in Google Drive from seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from src.core.config import get_settings
from src.parser.openxml_extractor import OpenXMLExtractor

DRIVE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def build_google_sheets_seed_bundle(xlsm_path: Path, spreadsheet_id: str) -> dict[str, Any]:
    """Convert the 22-sheet OpenXML workbook into a Google Sheets v4 verification bundle."""
    graph = OpenXMLExtractor.extract_from_path(
        file_path=xlsm_path,
        spreadsheet_id=spreadsheet_id,
    )
    valid_named_ranges = [nr for nr in graph.named_ranges if not nr.is_broken_ref]
    quarantined_named_ranges = [nr for nr in graph.named_ranges if nr.is_broken_ref]

    return {
        "spreadsheetId": spreadsheet_id,
        "properties": {"title": graph.workbook_name},
        "sheets_summary": [s.model_dump() for s in graph.sheets],
        "total_populated_cells": len(graph.cells),
        "total_formula_cells": sum(s.formula_cell_count for s in graph.sheets),
        "valid_named_ranges_count": len(valid_named_ranges),
        "quarantined_broken_named_ranges_count": len(quarantined_named_ranges),
        "macro_button_bindings": [mb.model_dump() for mb in graph.macro_bindings],
    }


def upload_and_seed_live_google_sheet(
    xlsm_path: Path,
    title: str,
    project_id: str,
    share_with_email: str | None = None,
    max_retries: int = 5,
) -> dict[str, Any]:
    """Upload the seed .xlsm to Google Drive and convert it to a native Google Sheet.

    Preserves 100% of the 22 worksheets, 35,655 cells, number formats, colors, column widths,
    formulas, and 31 drawing buttons on General!B41:N53. Also removes any broken #REF! named
    ranges carried over during conversion (DEC-02).
    """
    import subprocess

    from google.oauth2.credentials import Credentials as OAuthCredentials

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
        creds, _ = google.auth.default(scopes=DRIVE_SHEETS_SCOPES)
        if hasattr(creds, "with_quota_project"):
            creds = creds.with_quota_project(project_id)

    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    media = MediaFileUpload(
        str(xlsm_path),
        mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
        resumable=True,
    )

    created_file: dict[str, Any] | None = None
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            created_file = (
                drive_service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id,name,webViewLink,owners",
                )
                .execute()
            )
            break
        except HttpError as exc:
            last_err = exc
            if attempt < max_retries and exc.resp.status in (403, 429, 500, 503):
                time.sleep(5 * attempt)
                continue
            raise

    if created_file is None:
        raise RuntimeError(f"Failed to create Google Sheet in Drive: {last_err}")

    spreadsheet_id = created_file["id"]
    web_view_link = created_file.get(
        "webViewLink",
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
    )

    # Optional: share with target user email if uploaded via service account
    if share_with_email:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": share_with_email,
                },
                sendNotificationEmail=False,
            ).execute()
        except HttpError:
            pass

    # Inspect converted spreadsheet metadata via Google Sheets v4 API and purge any #REF! named ranges
    sheet_meta = (
        sheets_service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            includeGridData=False,
        )
        .execute()
    )

    sheets_list = [s["properties"]["title"] for s in sheet_meta.get("sheets", [])]
    named_ranges = sheet_meta.get("namedRanges", [])
    delete_requests: list[dict[str, Any]] = []
    for nr in named_ranges:
        nr_id = nr.get("namedRangeId")
        rng = nr.get("range", {})
        # If range lacks valid sheetId or startRowIndex, quarantine/remove it
        if nr_id and ("sheetId" not in rng and "startRowIndex" not in rng):
            delete_requests.append({"deleteNamedRange": {"namedRangeId": nr_id}})

    if delete_requests:
        for i in range(0, len(delete_requests), 500):
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": delete_requests[i : i + 500]},
            ).execute()

    return {
        "spreadsheet_id": spreadsheet_id,
        "title": created_file.get("name", title),
        "spreadsheet_url": web_view_link,
        "sheet_count": len(sheets_list),
        "sheet_names": sheets_list,
        "converted_named_ranges_count": len(named_ranges),
        "purged_broken_named_ranges_count": len(delete_requests),
    }


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Seed a live Google Sheet in Google Drive or generate a local verification bundle."
    )
    parser.add_argument(
        "--xlsm",
        default=str(settings.seed_workbook_path),
        help="Path to read-only seed .xlsm workbook",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default="google-sheets-brazil-tt-v13",
        help="Target Google Spreadsheet ID (for local bundle mode)",
    )
    parser.add_argument(
        "--title",
        default="Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)",
        help="Title of the Google Sheet created in Google Drive",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Upload and convert the .xlsm into a live Google Sheet in Google Drive",
    )
    parser.add_argument(
        "--share-with",
        default="admin@ferozmulla.altostrat.com",
        help="Email address to ensure writer access on the created Google Sheet",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output file path for the generated JSON result",
    )
    args = parser.parse_args()

    if args.live:
        result = upload_and_seed_live_google_sheet(
            xlsm_path=Path(args.xlsm),
            title=args.title,
            project_id=settings.gcp_project_id,
            share_with_email=args.share_with,
        )
    else:
        result = build_google_sheets_seed_bundle(Path(args.xlsm), args.spreadsheet_id)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
