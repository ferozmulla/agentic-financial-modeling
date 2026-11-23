#!/usr/bin/env python3
"""Side-by-side Cowork installer for `model-onboarding-mcp` and `onboard-energy-model-gcp` (leaves Brazil & EULR untouched)."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

ONBOARDING_ROOT = Path(__file__).resolve().parents[1]
MCP_CONFIG_KEY = "model-onboarding-mcp"
DEFAULT_SSE_URL = "https://model-onboarding-mcp-2wcxwkmdga-uc.a.run.app/mcp/sse"
SKILL_ID = "onboard-energy-model-gcp"


def _sync_skill_manifest_if_present(config_dir: Path, enable: bool) -> list[str]:
    """Update Cowork `manifest.json` for `onboard-energy-model-gcp` only, leaving all Brazil/EULR entries intact."""
    updated_manifests: list[str] = []
    skills_target = config_dir / "skills"
    for candidate in (skills_target / "manifest.json", config_dir / "manifest.json"):
        if not candidate.is_file():
            continue
        try:
            mdata = json.loads(candidate.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(mdata, dict) or not isinstance(mdata.get("skills"), dict):
            continue

        skills_map = dict(mdata["skills"])
        template_entry = (
            skills_map.get("eulr-refining-model-gcp")
            or skills_map.get("brazil-power-model-gcp")
            or skills_map.get("brazil-bqml-gcp")
        )
        if enable:
            existing = skills_map.get(SKILL_ID)
            if isinstance(existing, dict):
                entry = dict(existing)
            elif isinstance(template_entry, dict):
                entry = {}
                for k, v in template_entry.items():
                    if isinstance(v, str):
                        replaced = v
                        for old_sid in (
                            "eulr-refining-model-gcp",
                            "brazil-power-model-gcp",
                            "brazil-bqml-gcp",
                        ):
                            replaced = replaced.replace(old_sid, SKILL_ID)
                        for old_pkg in ("eulr-bq-twin", "brazil-power-bq-twin"):
                            replaced = replaced.replace(old_pkg, "model-onboarding")
                        entry[k] = replaced
                    else:
                        entry[k] = v
            else:
                entry = {}
            entry["status"] = "installed"
            entry["disabled"] = False
            entry["error"] = None
            skills_map[SKILL_ID] = entry
        else:
            skills_map.pop(SKILL_ID, None)

        mdata["skills"] = skills_map
        candidate.write_text(json.dumps(mdata, indent=2) + "\n", encoding="utf-8")
        updated_manifests.append(str(candidate))
    return updated_manifests


def configure_onboarding_in_cowork(
    config_dir: Path,
    server_sse_url: str,
    enable: bool = True,
) -> dict[str, Any]:
    """Add or remove ONLY `model-onboarding-mcp` and `onboard-energy-model-gcp`, leaving Brazil & EULR untouched."""
    config_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = config_dir / "mcp_config.json"
    data: dict[str, Any] = {}
    if mcp_path.is_file():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    servers = dict(data.get("mcpServers") or {})

    skills_target = config_dir / "skills"
    skills_target.mkdir(parents=True, exist_ok=True)
    dest_skill = skills_target / SKILL_ID

    if enable:
        if not server_sse_url.startswith("https://"):
            raise ValueError(f"server_sse_url must use HTTPS: {server_sse_url!r}")
        normalized_sse = (
            server_sse_url
            if server_sse_url.rstrip("/").endswith("/mcp/sse")
            else f"{server_sse_url.rstrip('/')}/mcp/sse"
        )
        servers[MCP_CONFIG_KEY] = {"serverUrl": normalized_sse}
        if dest_skill.exists():
            shutil.rmtree(dest_skill)
        shutil.copytree(ONBOARDING_ROOT / "skills" / SKILL_ID, dest_skill)
    else:
        servers.pop(MCP_CONFIG_KEY, None)
        if dest_skill.exists():
            shutil.rmtree(dest_skill)

    if mcp_path.is_file() or config_dir.name in {
        "config",
        "jetski",
        "antigravity",
        "cowork_workspace",
        ".cowork",
    }:
        data["mcpServers"] = servers
        mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    manifests_updated = _sync_skill_manifest_if_present(config_dir, enable=enable)
    return {
        "config_dir": str(config_dir),
        "enabled": enable,
        "mcp_servers_present": sorted(servers.keys()),
        "skill_installed": SKILL_ID if enable else None,
        "manifests_updated": manifests_updated,
    }


def resolve_default_cowork_dirs(home: Path | None = None) -> list[Path]:
    """Discover active Gemini/Jetski/Cowork config directories on Mac or Cloudtop."""
    base = (home or Path.home()).expanduser().resolve()
    targets: list[Path] = [base / ".gemini" / "config"]
    for extra in (
        base / ".gemini" / "jetski",
        base / "cowork_workspace",
        base / ".gemini" / "antigravity",
        base / ".cowork",
        base / ".coworkagent",
    ):
        if extra.is_dir() and extra not in targets:
            targets.append(extra)
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install model-onboarding-mcp and onboard-energy-model-gcp into Cowork (leaves Brazil & EULR untouched)."
    )
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SSE_URL,
        help="Cloud Run base URL or /mcp/sse URL of model-onboarding-mcp.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Optional explicit Cowork config directory; defaults to all discovered Cowork/Gemini dirs.",
    )
    parser.add_argument("--disable", action="store_true", help="Remove model-onboarding-mcp from Cowork.")
    args = parser.parse_args()

    if args.config_dir is not None:
        out: Any = configure_onboarding_in_cowork(
            config_dir=args.config_dir.expanduser().resolve(),
            server_sse_url=args.server_url,
            enable=not args.disable,
        )
    else:
        results: list[dict[str, Any]] = []
        for idx, target in enumerate(resolve_default_cowork_dirs()):
            try:
                results.append(
                    configure_onboarding_in_cowork(
                        config_dir=target,
                        server_sse_url=args.server_url,
                        enable=not args.disable,
                    )
                )
            except PermissionError as exc:
                if idx == 0:
                    raise
                results.append({"config_dir": str(target), "skipped": f"PermissionError: {exc}"})
        out = {"synced_targets": results}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
