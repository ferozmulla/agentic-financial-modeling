#!/usr/bin/env python3
"""Side-by-side Cowork installer for `eulr-refining-mcp` and the 5 `eulr-*-gcp` skills (leaves Brazil untouched)."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

TWIN_ROOT = Path(__file__).resolve().parents[1]
MCP_CONFIG_KEY = "eulr-refining-mcp"
SKILL_IDS = (
    "eulr-refining-model-gcp",
    "eulr-equilibrium-gcp",
    "eulr-scenario-matrix-gcp",
    "eulr-bqml-gcp",
    "eulr-hck-economics-gcp",
)


def configure_eulr_twin_in_cowork(
    config_dir: Path,
    server_sse_url: str,
    enable: bool = True,
) -> dict[str, Any]:
    """Add or remove `eulr-refining-mcp` and `eulr-*-gcp` skills without touching Brazil entries."""
    config_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = config_dir / "mcp_config.json"
    data: dict[str, Any] = {}
    if mcp_path.is_file():
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    servers = dict(data.get("mcpServers") or {})

    skills_target = config_dir / "skills"
    skills_target.mkdir(parents=True, exist_ok=True)

    if enable:
        servers[MCP_CONFIG_KEY] = {"serverUrl": server_sse_url}
        for sid in SKILL_IDS:
            dest = skills_target / sid
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(TWIN_ROOT / "skills" / sid, dest)
    else:
        servers.pop(MCP_CONFIG_KEY, None)
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
        "skills_installed": list(SKILL_IDS) if enable else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Wire isolated EULR Digital Twin into Cowork")
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".gemini" / "config")
    parser.add_argument("--server-url", required=True, help="Full /mcp/sse URL of eulr-bq-twin-mcp")
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()

    res = configure_eulr_twin_in_cowork(
        config_dir=args.config_dir.expanduser().resolve(),
        server_sse_url=args.server_url,
        enable=not args.disable,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
