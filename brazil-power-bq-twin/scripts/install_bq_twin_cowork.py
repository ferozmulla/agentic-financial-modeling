#!/usr/bin/env python3
"""Optional side-by-side Cowork installer for `brazil-power-bq-twin-mcp` and `bq-twin-*` skills."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

TWIN_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_NAME = "brazil-power-bq-twin-mcp"
DEFAULT_SSE_URL = "https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/mcp/sse"
SKILL_IDS = (
    "brazil-power-model-gcp",
    "brazil-tornado-gcp",
    "brazil-bqml-gcp",
    "brazil-lcoe-gcp",
    "brazil-dcf-gcp",
)


def configure_bq_twin_in_cowork(
    config_dir: Path,
    enable: bool = True,
    server_url: str = DEFAULT_SSE_URL,
) -> dict[str, Any]:
    """Add or remove `brazil-power-bq-twin-mcp` and `bq-twin-*` skills without touching `brazil-power-mcp`."""
    config_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = config_dir / "mcp_config.json"
    data: dict[str, Any] = {}
    if mcp_path.is_file():
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    servers = dict(data.get("mcpServers") or {})

    skills_target = config_dir / "skills"
    skills_target.mkdir(parents=True, exist_ok=True)

    if enable:
        servers[MCP_SERVER_NAME] = {"serverUrl": server_url}
        for sid in SKILL_IDS:
            dest = skills_target / sid
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(TWIN_ROOT / "skills" / sid, dest)
    else:
        servers.pop(MCP_SERVER_NAME, None)
        for sid in SKILL_IDS:
            dest = skills_target / sid
            if dest.exists():
                shutil.rmtree(dest)

    data["mcpServers"] = servers
    mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "config_dir": str(config_dir),
        "enabled": enable,
        "mcp_servers_present": sorted(servers.keys()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enable or disable isolated BigQuery Digital Twin in Cowork")
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".gemini" / "config")
    parser.add_argument("--disable", action="store_true", help="Remove bq-twin entries while preserving brazil-power-mcp")
    parser.add_argument("--server-url", default=DEFAULT_SSE_URL)
    args = parser.parse_args()

    res = configure_bq_twin_in_cowork(
        config_dir=args.config_dir.expanduser().resolve(),
        enable=not args.disable,
        server_url=args.server_url,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
