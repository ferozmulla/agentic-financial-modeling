"""Top-level re-export shim for brazil_power_agent.install_customizations."""

from __future__ import annotations

from brazil_power_agent.install_customizations import (
    EXPECTED_SKILLS,
    install_skills_and_mcp,
    parse_skill_frontmatter,
    resolve_target_config_dir,
    verify_skills_and_mcp_installed,
)

__all__ = [
    "EXPECTED_SKILLS",
    "install_skills_and_mcp",
    "parse_skill_frontmatter",
    "resolve_target_config_dir",
    "verify_skills_and_mcp_installed",
]
