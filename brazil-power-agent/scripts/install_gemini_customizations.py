#!/usr/bin/env python3
"""CLI script to install and verify the 5 Brazil Power v13 Gemini App skills and `brazil-power-mcp` server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SRC = REPO_ROOT / "brazil-power-agent" / "src"
V13_ROOT = REPO_ROOT / "brazil-power-v13"

for _p in (str(AGENT_SRC), str(V13_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brazil_power_agent.install_customizations import (
    install_skills_and_mcp,
    verify_skills_and_mcp_installed,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install or verify Brazil Power v13 Gemini App skills and brazil-power-mcp configuration."
    )
    parser.add_argument(
        "--target",
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Target Gemini configuration directory (e.g. ~/.gemini/config). Defaults to auto-resolved config dir.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing skills and MCP configuration without copying files.",
    )
    args = parser.parse_args(argv)

    if args.verify_only:
        status = verify_skills_and_mcp_installed(config_dir=args.config_dir, repo_root=REPO_ROOT)
    else:
        status = install_skills_and_mcp(config_dir=args.config_dir, repo_root=REPO_ROOT)

    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if status.get("all_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
