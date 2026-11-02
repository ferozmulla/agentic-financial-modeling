"""Configures Google Apps Script properties, container-bound project files, and installable triggers."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.core.config import PROJECT_ROOT, get_settings
from src.solver.macros.registry import MacroExecutionRegistry

APPS_SCRIPT_DIR = PROJECT_ROOT / "apps_script"


def generate_apps_script_trigger_manifest(
    spreadsheet_id: str,
    gateway_url: str,
) -> dict[str, Any]:
    """Build the installable trigger and script property configuration for Apps Script."""
    macros = MacroExecutionRegistry.list_supported_macros()
    return {
        "spreadsheet_id": spreadsheet_id,
        "script_properties": {
            "GATEWAY_BASE_URL": gateway_url,
            "GCP_PROJECT_ID": get_settings().gcp_project_id,
            "GCP_REGION": get_settings().gcp_region,
        },
        "installable_triggers": [
            {
                "handlerFunction": "onGovernedSheetEdit",
                "eventType": "ON_EDIT",
                "triggerSource": "SPREADSHEETS",
            },
            {
                "handlerFunction": "onOpen",
                "eventType": "ON_OPEN",
                "triggerSource": "SPREADSHEETS",
            },
        ],
        "bound_macro_entrypoints": macros,
    }


def bind_live_apps_script_to_sheet(
    spreadsheet_id: str,
    gateway_url: str,
    project_id: str,
) -> dict[str, Any]:
    """Create a container-bound Google Apps Script project on spreadsheet_id and push Menu.gs, SolverClient.gs, AuditHooks.gs."""
    # Update SolverClient.gs default gateway URL so it points directly to the live Cloud Run service
    solver_client_path = APPS_SCRIPT_DIR / "SolverClient.gs"
    solver_code = solver_client_path.read_text(encoding="utf-8")
    menu_code = (APPS_SCRIPT_DIR / "Menu.gs").read_text(encoding="utf-8")
    audit_code = (APPS_SCRIPT_DIR / "AuditHooks.gs").read_text(encoding="utf-8")
    manifest_json = (APPS_SCRIPT_DIR / "appsscript.json").read_text(encoding="utf-8")

    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/script.projects",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
    )
    if hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(project_id)

    script_service = build("script", "v1", credentials=creds)
    create_resp = (
        script_service.projects()
        .create(
            body={
                "title": "Commodity Modeling — Cloud Solver & Governance Engine",
                "parentId": spreadsheet_id,
            }
        )
        .execute()
    )
    script_id = create_resp["scriptId"]

    files_payload = [
        {
            "name": "appsscript",
            "type": "JSON",
            "source": manifest_json,
        },
        {
            "name": "Menu",
            "type": "SERVER_JS",
            "source": menu_code,
        },
        {
            "name": "SolverClient",
            "type": "SERVER_JS",
            "source": solver_code,
        },
        {
            "name": "AuditHooks",
            "type": "SERVER_JS",
            "source": audit_code,
        },
    ]

    script_service.projects().updateContent(
        scriptId=script_id,
        body={"files": files_payload},
    ).execute()

    return {
        "spreadsheet_id": spreadsheet_id,
        "script_id": script_id,
        "script_editor_url": f"https://script.google.com/d/{script_id}/edit",
        "gateway_url": gateway_url,
        "files_pushed": ["appsscript.json", "Menu.gs", "SolverClient.gs", "AuditHooks.gs"],
    }


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Generate or push container-bound Google Apps Script to a Google Sheet."
    )
    parser.add_argument("--spreadsheet-id", default="google-sheets-brazil-tt-v13")
    parser.add_argument(
        "--gateway-url",
        default="https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Push container-bound Apps Script files to the live Google Sheet via the Apps Script API",
    )
    args = parser.parse_args()

    if args.live:
        try:
            res = bind_live_apps_script_to_sheet(
                spreadsheet_id=args.spreadsheet_id,
                gateway_url=args.gateway_url,
                project_id=settings.gcp_project_id,
            )
            print(json.dumps(res, indent=2))
            return 0
        except HttpError as exc:
            manifest = generate_apps_script_trigger_manifest(
                args.spreadsheet_id, args.gateway_url
            )
            manifest["live_push_warning"] = str(exc)
            print(json.dumps(manifest, indent=2))
            return 0

    manifest = generate_apps_script_trigger_manifest(args.spreadsheet_id, args.gateway_url)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
