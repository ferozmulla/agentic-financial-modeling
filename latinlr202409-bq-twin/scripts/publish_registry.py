#!/usr/bin/env python3
"""Publish MCP server and Analyst Guided Skills to Agent Registry."""

from __future__ import annotations

import json
from pathlib import Path

from latinlr202409_bq_twin.config import settings
from latinlr202409_bq_twin.mcp_tools import build_standard_7_tools


def main() -> None:
    print("Collecting standard 7-tool MCP schemas...")
    dataset_fqn = f"{settings.project_id}.{settings.dataset_id}"
    tools = build_standard_7_tools("latinlr202409", "Latinlr202409 Crude Model", dataset_fqn)
    print(f"Loaded {len(tools)} remote MCP tool schemas:")
    for t in tools:
        print(f"  - {t['name']}: {t['description'][:80]}...")

    print("\nLocating Analyst Skill markdown files...")
    skills_dir = Path(__file__).parent.parent / "skills"
    if skills_dir.is_dir():
        for skill_path in skills_dir.glob("**/SKILL.md"):
            print(f"  - Found: {skill_path.relative_to(skills_dir.parent)}")
    else:
        print("  - No skills directory found.")

    print("\nAgent Registry publishing completed successfully (Dry-Run).")


if __name__ == "__main__":
    main()
