#!/usr/bin/env python3
"""Publish `latinlr202409-bq-twin-mcp` and `latinlr202409-model-gcp` skill to Google Cloud Agent Registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from latinlr202409_bq_twin.mcp_tools import MCP_SERVER_NAME, TWIN_MCP_TOOLS


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish MCP server and skill metadata.")
    parser.add_argument("--cloud-run-url", type=str, default="https://latinlr202409-bq-twin-mcp-2wcxwkmdga-uc.a.run.app")
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "service": MCP_SERVER_NAME,
                "endpoint": f"{args.cloud_run_url.rstrip('/')}/mcp",
                "tools": [t["name"] for t in TWIN_MCP_TOOLS],
                "skill": "latinlr202409-model-gcp",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
