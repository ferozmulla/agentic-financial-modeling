#!/usr/bin/env python3
"""Publish `brazil-power-mcp` (MCP Server) and the 5 Brazil Power v13 Skills to Google Cloud Agent Registry."""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(WORKSPACE_ROOT / "brazil-power-agent" / "src"), str(WORKSPACE_ROOT / "brazil-power-v13")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brazil_power_agent.install_customizations import EXPECTED_SKILLS, parse_skill_frontmatter
from brazil_power_agent.mcp_server import MCP_TOOLS

AGENT_REGISTRY_MCP_URL = "https://agentregistry.googleapis.com/mcp"
DEFAULT_PROJECT_ID = "comm-model-mod"
DEFAULT_LOCATION = "global"
DEFAULT_CLOUD_RUN_URL = "https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app"


def _get_access_token() -> str:
    """Obtain an OAuth2 access token from Application Default Credentials."""
    import google.auth
    from google.auth.transport.requests import Request

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return str(creds.token)


def call_agent_registry_tool(
    tool_name: str,
    arguments: dict[str, Any],
    token: str,
    project_id: str = DEFAULT_PROJECT_ID,
) -> dict[str, Any]:
    """Invoke a tool on Google Cloud's `https://agentregistry.googleapis.com/mcp` endpoint."""
    req_body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        AGENT_REGISTRY_MCP_URL,
        data=req_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45.0) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} calling Agent Registry {tool_name}: {err_text}") from exc

    if "error" in envelope:
        raise RuntimeError(f"JSON-RPC error calling {tool_name}: {json.dumps(envelope['error'])}")

    result = envelope.get("result") or {}
    if result.get("isError"):
        raise RuntimeError(f"Tool error calling {tool_name}: {json.dumps(result.get('content'))}")

    if "structuredContent" in result and isinstance(result["structuredContent"], dict):
        return result["structuredContent"]

    text_items = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)]
    joined = "\n".join(text_items).strip()
    if joined.startswith("{") or joined.startswith("["):
        return json.loads(joined)
    return {"raw_text": joined}


def _build_skill_zip_base64(skill_dir: Path) -> str:
    """Package a skill directory (containing SKILL.md and any supporting files) into a base64-encoded ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(skill_dir.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                rel_name = file_path.relative_to(skill_dir).as_posix()
                zf.writestr(rel_name, file_path.read_bytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def register_mcp_server_in_agent_registry(
    token: str,
    project_id: str = DEFAULT_PROJECT_ID,
    location: str = DEFAULT_LOCATION,
    cloud_run_url: str = DEFAULT_CLOUD_RUN_URL,
    service_id: str = "brazil-power-mcp",
) -> dict[str, Any]:
    """Create or update `brazil-power-mcp` in Google Cloud Agent Registry -> MCP Servers."""
    parent = f"projects/{project_id}/locations/{location}"
    service_name = f"{parent}/services/{service_id}"
    mcp_endpoint = f"{cloud_run_url.rstrip('/')}/mcp"

    service_payload: dict[str, Any] = {
        "displayName": "brazil-power-mcp",
        "description": (
            "Brazil Energy Model (v13) Remote MCP Server — 22-Tab Power Generation Techno-Economic Solver "
            "(General!B5:N40 Assumptions, 21-Point Tornado IRR, Live BigQuery ML ARIMA_PLUS Refresh, "
            "23-Year LCOE Horizon, 30-Year DCF & CVU/GF Sweep, and 22-Tab .xlsx / Google Sheets Exporter)."
        ),
        "interfaces": [
            {
                "protocolBinding": "JSONRPC",
                "url": mcp_endpoint,
            }
        ],
        "mcpServerSpec": {
            "type": "TOOL_SPEC",
            "content": {
                "tools": MCP_TOOLS,
            },
        },
    }

    existing = call_agent_registry_tool("list_services", {"parent": parent}, token, project_id=project_id)
    services_list = existing.get("services") or []
    exists = any(s.get("name") == service_name or str(s.get("name", "")).endswith(f"/services/{service_id}") for s in services_list)

    if exists:
        op = call_agent_registry_tool(
            "update_service",
            {
                "service": {"name": service_name, **service_payload},
                "updateMask": "displayName,description,interfaces,mcpServerSpec",
            },
            token,
            project_id=project_id,
        )
        action = "updated"
    else:
        op = call_agent_registry_tool(
            "create_service",
            {
                "parent": parent,
                "serviceId": service_id,
                "service": service_payload,
            },
            token,
            project_id=project_id,
        )
        action = "created"

    # Poll briefly so registryResource is populated
    time.sleep(2.0)
    svc_detail: dict[str, Any] = {}
    try:
        svc_detail = call_agent_registry_tool("get_service", {"name": service_name}, token, project_id=project_id)
    except Exception:
        svc_detail = op

    return {
        "action": action,
        "service_name": service_name,
        "mcp_endpoint": mcp_endpoint,
        "tool_count": len(MCP_TOOLS),
        "service": svc_detail,
    }


def register_skills_in_agent_registry(
    token: str,
    project_id: str = DEFAULT_PROJECT_ID,
    location: str = DEFAULT_LOCATION,
) -> list[dict[str, Any]]:
    """Create or update all 5 Brazil Power v13 Skills in Google Cloud Agent Registry -> Skills (Preview)."""
    parent = f"projects/{project_id}/locations/{location}"
    skills_root = WORKSPACE_ROOT / "brazil-power-agent" / "skills"

    results: list[dict[str, Any]] = []
    for skill_id in EXPECTED_SKILLS:
        skill_dir = skills_root / skill_id
        skill_md_path = skill_dir / "SKILL.md"
        fm = parse_skill_frontmatter(skill_md_path.read_text(encoding="utf-8"))
        display_name = f"Brazil Power v13 — {skill_id}"
        description = (fm.get("description") or f"Brazil Power v13 {skill_id} workflow")[:2000]
        zip_b64 = _build_skill_zip_base64(skill_dir)
        private_resource_name = f"{parent}/skills/private-{skill_id}"
        matched: dict[str, Any] | None = None
        try:
            matched = call_agent_registry_tool(
                "get_skill",
                {"name": private_resource_name},
                token,
                project_id=project_id,
            )
        except Exception:
            matched = None
        skill_resource_name = str(matched["name"]) if matched else private_resource_name

        if matched is None:
            op = call_agent_registry_tool(
                "create_skill",
                {
                    "parent": parent,
                    "skillId": skill_id,
                    "skill": {
                        "displayName": display_name,
                        "description": description,
                        "type": "SIMPLE",
                        "targetState": "TARGET_STATE_ACTIVE",
                        "initialRevision": {
                            "archiveUploadSource": {
                                "archiveContent": zip_b64,
                            }
                        },
                    },
                },
                token,
                project_id=project_id,
            )
            action = "created"
        else:
            rev_id = f"rev-{int(time.time())}"
            rev_op = call_agent_registry_tool(
                "create_skill_revision",
                {
                    "parent": skill_resource_name,
                    "skillRevisionId": rev_id,
                    "skillRevision": {
                        "archiveUploadSource": {
                            "archiveContent": zip_b64,
                        }
                    },
                },
                token,
                project_id=project_id,
            )
            op = call_agent_registry_tool(
                "update_skill",
                {
                    "skill": {
                        "name": skill_resource_name,
                        "displayName": display_name,
                        "description": description,
                        "type": "SIMPLE",
                        "targetState": "TARGET_STATE_ACTIVE",
                    },
                    "updateMask": "displayName,description,targetState",
                },
                token,
                project_id=project_id,
            )
            op["revision_operation"] = rev_op
            action = "updated"

        results.append(
            {
                "skill_id": skill_id,
                "action": action,
                "resource_name": skill_resource_name,
                "operation": op,
            }
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register brazil-power-mcp and the 5 Brazil Power v13 skills in Google Cloud Agent Registry."
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="GCP Project ID")
    parser.add_argument("--location", default=DEFAULT_LOCATION, help="Agent Registry location (default: global)")
    parser.add_argument("--cloud-run-url", default=DEFAULT_CLOUD_RUN_URL, help="Cloud Run base URL")
    parser.add_argument("--skip-skills", action="store_true", help="Only register the MCP server")
    args = parser.parse_args()

    token = _get_access_token()
    mcp_res = register_mcp_server_in_agent_registry(
        token=token,
        project_id=args.project_id,
        location=args.location,
        cloud_run_url=args.cloud_run_url,
    )
    skills_res: list[dict[str, Any]] = []
    if not args.skip_skills:
        skills_res = register_skills_in_agent_registry(
            token=token,
            project_id=args.project_id,
            location=args.location,
        )

    print(
        json.dumps(
            {
                "project_id": args.project_id,
                "location": args.location,
                "mcp_server_registration": mcp_res,
                "skills_registration": skills_res,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
