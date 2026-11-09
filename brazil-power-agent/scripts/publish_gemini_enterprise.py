#!/usr/bin/env python3
"""Register or update the Brazil Power v13 Cloud Run A2A Agent with Gemini Enterprise."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(WORKSPACE_ROOT / "brazil-power-agent" / "src"), str(WORKSPACE_ROOT / "brazil-power-v13")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.api.routes.agent_cloud import GEMINI_ENTERPRISE_ENGINE_NAME, build_a2a_agent_card

DEFAULT_CLOUD_RUN_URL = "https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app"


def _get_access_token() -> str:
    """Obtain an OAuth2 access token from Application Default Credentials."""
    import google.auth
    from google.auth.transport.requests import Request

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return str(creds.token)


def _api_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    project_id: str = "comm-model-mod",
) -> dict[str, Any]:
    """Perform an authenticated Discovery Engine v1alpha REST API request."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} calling {method} {url}: {err_body}") from exc


def register_or_update_a2a_agent(
    cloud_run_url: str = DEFAULT_CLOUD_RUN_URL,
    engine_name: str = GEMINI_ENTERPRISE_ENGINE_NAME,
    location: str = "us",
) -> dict[str, Any]:
    """Register or update the Brazil Power v13 A2A agent on Gemini Enterprise."""
    token = _get_access_token()
    card = build_a2a_agent_card(base_url=cloud_run_url)
    agents_base_url = (
        f"https://{location}-discoveryengine.googleapis.com/v1alpha/"
        f"{engine_name}/assistants/default_assistant/agents"
    )

    agent_body: dict[str, Any] = {
        "displayName": card["displayName"],
        "description": card["description"],
        "a2aAgentDefinition": {
            "jsonAgentCard": json.dumps(card),
        },
    }

    existing_agents = _api_request("GET", agents_base_url, token).get("agents", [])
    matched_agent: dict[str, Any] | None = None
    for ag in existing_agents:
        if ag.get("displayName") == card["displayName"] or "brazil_power_v13_agent" in json.dumps(ag):
            matched_agent = ag
            break

    if matched_agent and matched_agent.get("name"):
        agent_resource_name = matched_agent["name"]
        patch_url = (
            f"https://{location}-discoveryengine.googleapis.com/v1alpha/"
            f"{agent_resource_name}?updateMask=displayName,description,a2aAgentDefinition"
        )
        res = _api_request("PATCH", patch_url, token, payload=agent_body)
        action = "updated"
    else:
        res = _api_request("POST", agents_base_url, token, payload=agent_body)
        action = "created"

    return {
        "action": action,
        "engine_name": engine_name,
        "cloud_run_url": cloud_run_url,
        "agent_card_url": f"{cloud_run_url.rstrip('/')}/a2a/app/.well-known/agent-card.json",
        "agent_resource": res,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Brazil Power v13 A2A Agent to Gemini Enterprise")
    parser.add_argument("--cloud-run-url", default=DEFAULT_CLOUD_RUN_URL, help="Cloud Run base URL")
    parser.add_argument("--engine-name", default=GEMINI_ENTERPRISE_ENGINE_NAME, help="Discovery Engine full resource name")
    args = parser.parse_args()

    result = register_or_update_a2a_agent(
        cloud_run_url=args.cloud_run_url,
        engine_name=args.engine_name,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
