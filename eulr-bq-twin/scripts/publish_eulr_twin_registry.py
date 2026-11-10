#!/usr/bin/env python3
"""Publish `eulr-bq-twin-mcp` and the 5 `eulr-*-gcp` Skills to Google Cloud Agent Registry."""

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

TWIN_ROOT = Path(__file__).resolve().parents[1]
if str(TWIN_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(TWIN_ROOT / "src"))

from eulr_bq_twin.mcp_tools import EULR_TWIN_MCP_TOOLS, MCP_SERVER_NAME

AGENT_REGISTRY_MCP_URL = "https://agentregistry.googleapis.com/mcp"
DEFAULT_PROJECT_ID = "comm-model-mod"
DEFAULT_LOCATION = "global"

EULR_SKILL_IDS: tuple[str, ...] = (
    "eulr-refining-model-gcp",
    "eulr-equilibrium-gcp",
    "eulr-scenario-matrix-gcp",
    "eulr-bqml-gcp",
    "eulr-hck-economics-gcp",
)


def _get_token() -> str:
    import google.auth
    from google.auth.transport.requests import Request

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return str(creds.token)


def _call_registry(tool_name: str, arguments: dict[str, Any], token: str, project_id: str) -> dict[str, Any]:
    req = urllib.request.Request(
        AGENT_REGISTRY_MCP_URL,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ).encode("utf-8"),
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
        raise RuntimeError(f"HTTP {exc.code} calling {tool_name}: {exc.read().decode('utf-8', 'replace')}") from exc

    res = envelope.get("result") or {}
    if res.get("isError"):
        raise RuntimeError(f"Tool error in {tool_name}: {res.get('content')}")
    if "structuredContent" in res and isinstance(res["structuredContent"], dict):
        return res["structuredContent"]
    txt = "\n".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict)).strip()
    return json.loads(txt) if txt.startswith("{") else {"raw": txt}


def _parse_frontmatter(md_text: str) -> dict[str, str]:
    lines = md_text.lstrip().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def _zip_skill_b64(skill_dir: Path) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(skill_dir.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                zf.writestr(p.relative_to(skill_dir).as_posix(), p.read_bytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def publish_eulr_twin_to_agent_registry(
    cloud_run_url: str,
    project_id: str = DEFAULT_PROJECT_ID,
    location: str = DEFAULT_LOCATION,
) -> dict[str, Any]:
    token = _get_token()
    parent = f"projects/{project_id}/locations/{location}"
    service_name = f"{parent}/services/{MCP_SERVER_NAME}"
    mcp_endpoint = f"{cloud_run_url.rstrip('/')}/mcp"

    svc_body: dict[str, Any] = {
        "displayName": MCP_SERVER_NAME,
        "description": (
            "Isolated BigQuery Digital Twin Remote MCP Server for EULR European Refining Equilibrium "
            "(comm-model-mod.eulr_digital_twin — 19-sheet zero-Excel Digital Twin, 10-pass Gauss-Seidel "
            "equilibrium solver, EU ETS & 3-peer sync matrix, ARIMA_PLUS forecasts, HCK IRR, and 18/19-tab .xlsx synthesis)."
        ),
        "interfaces": [{"protocolBinding": "JSONRPC", "url": mcp_endpoint}],
        "mcpServerSpec": {"type": "TOOL_SPEC", "content": {"tools": EULR_TWIN_MCP_TOOLS}},
    }

    existing_svcs = _call_registry("list_services", {"parent": parent}, token, project_id).get("services") or []
    has_svc = any(str(s.get("name", "")).endswith(f"/services/{MCP_SERVER_NAME}") for s in existing_svcs)
    if has_svc:
        _call_registry(
            "update_service",
            {
                "service": {"name": service_name, **svc_body},
                "updateMask": "displayName,description,interfaces,mcpServerSpec",
            },
            token,
            project_id,
        )
        svc_action = "updated"
    else:
        _call_registry(
            "create_service",
            {"parent": parent, "serviceId": MCP_SERVER_NAME, "service": svc_body},
            token,
            project_id,
        )
        svc_action = "created"

    time.sleep(2.0)
    svc_info = _call_registry("get_service", {"name": service_name}, token, project_id)

    skill_results: list[dict[str, Any]] = []
    for sid in EULR_SKILL_IDS:
        sdir = TWIN_ROOT / "skills" / sid
        fm = _parse_frontmatter((sdir / "SKILL.md").read_text(encoding="utf-8"))
        display_name = f"EULR European Refining BQ Digital Twin — {sid}"
        desc = (fm.get("description") or display_name)[:2000]
        zb64 = _zip_skill_b64(sdir)
        priv_name = f"{parent}/skills/private-{sid}"

        matched: dict[str, Any] | None = None
        try:
            matched = _call_registry("get_skill", {"name": priv_name}, token, project_id)
        except Exception:
            matched = None

        if matched is None:
            op = _call_registry(
                "create_skill",
                {
                    "parent": parent,
                    "skillId": sid,
                    "skill": {
                        "displayName": display_name,
                        "description": desc,
                        "type": "SIMPLE",
                        "targetState": "TARGET_STATE_ACTIVE",
                        "initialRevision": {"archiveUploadSource": {"archiveContent": zb64}},
                    },
                },
                token,
                project_id,
            )
            s_action = "created"
        else:
            rev_id = f"rev-{int(time.time())}"
            _call_registry(
                "create_skill_revision",
                {
                    "parent": priv_name,
                    "skillRevisionId": rev_id,
                    "skillRevision": {"archiveUploadSource": {"archiveContent": zb64}},
                },
                token,
                project_id,
            )
            op = _call_registry(
                "update_skill",
                {
                    "skill": {
                        "name": priv_name,
                        "displayName": display_name,
                        "description": desc,
                        "type": "SIMPLE",
                        "targetState": "TARGET_STATE_ACTIVE",
                    },
                    "updateMask": "displayName,description,targetState",
                },
                token,
                project_id,
            )
            s_action = "updated"

        skill_results.append({"skill_id": sid, "action": s_action, "resource": priv_name, "op": op})

    return {
        "mcp_server": {"action": svc_action, "service": svc_info},
        "skills": skill_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish eulr-bq-twin-mcp and eulr-*-gcp skills to Agent Registry")
    parser.add_argument("--cloud-run-url", required=True)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    args = parser.parse_args()

    out = publish_eulr_twin_to_agent_registry(
        cloud_run_url=args.cloud_run_url,
        project_id=args.project_id,
        location=args.location,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
