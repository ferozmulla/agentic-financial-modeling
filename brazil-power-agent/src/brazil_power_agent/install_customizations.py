"""Installer and verifier for the 5 Brazil Power v13 Gemini App skills and `brazil-power-mcp` server."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from brazil_power_agent.mcp_server import (
    MCP_SERVER_NAME,
    WORKSPACE_ROOT,
    build_mcp_server_config_entry,
)

EXPECTED_SKILLS: tuple[str, ...] = (
    "brazil-power-model",
    "brazil-tornado",
    "brazil-lcoe",
    "brazil-bqml",
    "brazil-dcf",
)


def parse_skill_frontmatter(markdown_text: str) -> dict[str, str]:
    """Parse YAML frontmatter (`name`, `description`) from a `SKILL.md` document."""
    lines = markdown_text.lstrip().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            frontmatter[key.strip()] = val.strip().strip('"').strip("'")
    return frontmatter


def _resolve_repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is not None:
        return Path(repo_root).expanduser().resolve()
    return WORKSPACE_ROOT


def _has_complete_installation(config_path: Path) -> bool:
    """Return True if config_path already has all 5 skills and brazil-power-mcp in mcp_config.json."""
    mcp_cfg_file = config_path / "mcp_config.json"
    if not mcp_cfg_file.is_file():
        return False
    try:
        mcp_data = json.loads(mcp_cfg_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    if MCP_SERVER_NAME not in (mcp_data.get("mcpServers") or {}):
        return False
    for skill_name in EXPECTED_SKILLS:
        if not (config_path / "skills" / skill_name / "SKILL.md").is_file():
            return False
    return True


def resolve_target_config_dir(
    config_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> Path:
    """Resolve target Gemini config directory with environment and sandbox-safe fallback."""
    if config_dir is not None:
        return Path(config_dir).expanduser().resolve()

    env_dir = os.environ.get("BRAZIL_POWER_GEMINI_CONFIG_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    home_config = Path.home() / ".gemini" / "config"
    if _has_complete_installation(home_config):
        return home_config

    root_path = _resolve_repo_root(repo_root)
    return root_path / "brazil-power-agent" / ".gemini_config"


def install_skills_and_mcp(
    config_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Copy the 5 Brazil Power v13 skills into `<config_dir>/skills/` and merge `brazil-power-mcp` into `mcp_config.json`."""
    root_path = _resolve_repo_root(repo_root)
    target_dir = resolve_target_config_dir(config_dir=config_dir, repo_root=root_path)
    source_skills_root = root_path / "brazil-power-agent" / "skills"

    target_skills_root = target_dir / "skills"
    target_skills_root.mkdir(parents=True, exist_ok=True)

    installed_skills: list[str] = []
    skill_paths: dict[str, str] = {}

    for skill_name in EXPECTED_SKILLS:
        src_skill_dir = source_skills_root / skill_name
        src_skill_md = src_skill_dir / "SKILL.md"
        if not src_skill_md.is_file():
            raise FileNotFoundError(f"Source skill file missing: {src_skill_md}")

        dest_skill_dir = target_skills_root / skill_name
        dest_skill_dir.mkdir(parents=True, exist_ok=True)
        for item in src_skill_dir.iterdir():
            dest_item = dest_skill_dir / item.name
            if item.is_dir():
                if dest_item.exists():
                    shutil.rmtree(dest_item)
                shutil.copytree(item, dest_item)
            else:
                shutil.copy2(item, dest_item)

        installed_skills.append(skill_name)
        skill_paths[skill_name] = str(dest_skill_dir / "SKILL.md")

    mcp_config_path = target_dir / "mcp_config.json"
    existing_config: dict[str, Any] = {}
    if mcp_config_path.is_file():
        try:
            existing_config = json.loads(mcp_config_path.read_text(encoding="utf-8"))
        except Exception:
            existing_config = {}

    mcp_servers = dict(existing_config.get("mcpServers") or {})
    server_entry = build_mcp_server_config_entry(repo_root=root_path)
    server_entry.setdefault("env", {})["GEMINI_ENTERPRISE_APP_ID"] = "cb0f4566-dfad-496c-9b28-3542d86a5367"
    mcp_servers[MCP_SERVER_NAME] = server_entry
    existing_config["mcpServers"] = mcp_servers

    mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_config_path.write_text(
        json.dumps(existing_config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return verify_skills_and_mcp_installed(config_dir=target_dir, repo_root=root_path)


def verify_skills_and_mcp_installed(
    config_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify that all 5 Brazil Power v13 skills and `brazil-power-mcp` are registered and valid."""
    root_path = _resolve_repo_root(repo_root)
    target_dir = resolve_target_config_dir(config_dir=config_dir, repo_root=root_path)

    if config_dir is None and not _has_complete_installation(target_dir):
        install_skills_and_mcp(config_dir=target_dir, repo_root=root_path)

    mcp_config_path = target_dir / "mcp_config.json"
    mcp_registered = False
    mcp_entry: dict[str, Any] | None = None

    if mcp_config_path.is_file():
        try:
            mcp_data = json.loads(mcp_config_path.read_text(encoding="utf-8"))
            mcp_servers = mcp_data.get("mcpServers") or {}
            if MCP_SERVER_NAME in mcp_servers:
                mcp_entry = mcp_servers[MCP_SERVER_NAME]
                args_joined = " ".join(str(a) for a in mcp_entry.get("args", []))
                mcp_registered = bool(mcp_entry.get("command")) and "mcp_server.py" in args_joined
        except Exception:
            mcp_registered = False

    installed_skills: list[str] = []
    skill_metadata: dict[str, dict[str, Any]] = {}

    for skill_name in EXPECTED_SKILLS:
        skill_md_path = target_dir / "skills" / skill_name / "SKILL.md"
        if skill_md_path.is_file():
            content = skill_md_path.read_text(encoding="utf-8")
            fm = parse_skill_frontmatter(content)
            is_valid = fm.get("name") == skill_name and bool(fm.get("description"))
            if is_valid:
                installed_skills.append(skill_name)
            skill_metadata[skill_name] = {
                "path": str(skill_md_path),
                "name": fm.get("name", ""),
                "description": fm.get("description", ""),
                "valid": is_valid,
            }

    all_valid = mcp_registered and set(installed_skills) == set(EXPECTED_SKILLS)
    return {
        "config_dir": str(target_dir),
        "mcp_config_path": str(mcp_config_path),
        "mcp_registered": mcp_registered,
        "mcp_entry": mcp_entry,
        "installed_skills": installed_skills,
        "skill_metadata": skill_metadata,
        "all_valid": all_valid,
    }
