"""Tests for the 5 Brazil Power v13 Gemini App skills and MCP customization installer."""

from __future__ import annotations

import json
from pathlib import Path

from brazil_power_agent.install_customizations import (
    EXPECTED_SKILLS,
    install_skills_and_mcp,
    parse_skill_frontmatter,
    verify_skills_and_mcp_installed,
)


def test_all_five_skills_and_mcp_registered() -> None:
    status = verify_skills_and_mcp_installed()
    assert status["mcp_registered"] is True
    assert set(status["installed_skills"]) == {
        "brazil-power-model",
        "brazil-tornado",
        "brazil-lcoe",
        "brazil-bqml",
        "brazil-dcf",
    }


def test_install_skills_and_mcp_to_custom_config_dir(tmp_path: Path) -> None:
    # Seed a pre-existing MCP server in mcp_config.json to ensure preservation
    mcp_config_path = tmp_path / "mcp_config.json"
    mcp_config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "data-agent-kit": {
                        "command": "python3",
                        "args": ["-m", "data_agent_kit"],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = install_skills_and_mcp(config_dir=tmp_path)
    assert result["mcp_registered"] is True
    assert set(result["installed_skills"]) == set(EXPECTED_SKILLS)

    # Verify pre-existing MCP server was preserved alongside brazil-power-mcp
    merged_config = json.loads(mcp_config_path.read_text(encoding="utf-8"))
    assert "data-agent-kit" in merged_config["mcpServers"]
    assert "brazil-power-mcp" in merged_config["mcpServers"]
    mcp_entry = merged_config["mcpServers"]["brazil-power-mcp"]
    assert "mcp_server.py" in " ".join(mcp_entry.get("args", []))
    assert "PYTHONPATH" in mcp_entry.get("env", {})

    # Verify each installed SKILL.md has valid frontmatter and required workflow content
    for skill_name in EXPECTED_SKILLS:
        skill_path = tmp_path / "skills" / skill_name / "SKILL.md"
        assert skill_path.is_file(), f"Missing installed skill file: {skill_path}"
        content = skill_path.read_text(encoding="utf-8")
        frontmatter = parse_skill_frontmatter(content)
        assert frontmatter.get("name") == skill_name
        assert len(frontmatter.get("description", "")) > 20

        # Required interactive cards, MCP tools, Excel coordinates, charts, Artifacts, and 22-tab export
        assert "ask_question" in content
        assert "brazil-power-mcp" in content
        assert "General!B5:N40" in content
        assert "Output_1" in content
        assert "Output_3!B8:J31" in content
        assert "_01_CF" in content and "_12_CF" in content
        assert "render_chart" in content
        assert "Artifact" in content
        assert "export_full_22tab_workbook" in content
        assert "22-tab" in content.lower()
        assert "ZERO PRE-CARD TOOL CALLS" in content
        assert "artifact_file_uri" in content
        assert "--compact-llm" in content

    # Verify Cause 2 sequential question flow is preserved in brazil-power-model/SKILL.md
    master_skill = (tmp_path / "skills" / "brazil-power-model" / "SKILL.md").read_text(encoding="utf-8")
    assert "Step 2: Apply Any Assumption Overrides & Immediately Present Card 2" in master_skill
    assert "Step 3: Card 2 — Sequential Interactive Analysis Selection Card (`ask_question`)" in master_skill

    status = verify_skills_and_mcp_installed(config_dir=tmp_path)
    assert status["mcp_registered"] is True
    assert set(status["installed_skills"]) == set(EXPECTED_SKILLS)
    assert status["all_valid"] is True

