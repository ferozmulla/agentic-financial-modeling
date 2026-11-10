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
DEFAULT_SSE_URL = "https://eulr-bq-twin-mcp-2wcxwkmdga-uc.a.run.app/mcp/sse"
SKILL_IDS = (
    "eulr-refining-model-gcp",
    "eulr-equilibrium-gcp",
    "eulr-scenario-matrix-gcp",
    "eulr-bqml-gcp",
    "eulr-hck-economics-gcp",
)


def _sync_skill_manifest_if_present(config_dir: Path, enable: bool) -> list[str]:
    """If Cowork maintains a `manifest.json` index, register or remove `eulr-*-gcp` entries cleanly."""
    updated_manifests: list[str] = []
    skills_target = config_dir / "skills"
    for candidate in (skills_target / "manifest.json", config_dir / "manifest.json"):
        if not candidate.is_file():
            continue
        try:
            mdata = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(mdata, dict) or not isinstance(mdata.get("skills"), dict):
            continue
        skills_map = dict(mdata["skills"])
        template_entry = skills_map.get("brazil-bqml-gcp") or skills_map.get("brazil-power-model-gcp")
        for sid in SKILL_IDS:
            if enable:
                existing = skills_map.get(sid)
                if isinstance(existing, dict):
                    entry = dict(existing)
                elif isinstance(template_entry, dict):
                    entry = {}
                    for k, v in template_entry.items():
                        if isinstance(v, str) and "brazil-bqml-gcp" in v:
                            entry[k] = v.replace("brazil-bqml-gcp", sid).replace("brazil-power-bq-twin", "eulr-bq-twin")
                        elif isinstance(v, str) and "brazil-power-model-gcp" in v:
                            entry[k] = v.replace("brazil-power-model-gcp", sid).replace("brazil-power-bq-twin", "eulr-bq-twin")
                        else:
                            entry[k] = v
                else:
                    entry = {}
                entry["status"] = "installed"
                entry["disabled"] = False
                entry["error"] = None
                skills_map[sid] = entry
            else:
                skills_map.pop(sid, None)
        mdata["skills"] = skills_map
        candidate.write_text(json.dumps(mdata, indent=2) + "\n", encoding="utf-8")
        updated_manifests.append(str(candidate))
    return updated_manifests


def configure_eulr_twin_in_cowork(
    config_dir: Path,
    server_sse_url: str = DEFAULT_SSE_URL,
    enable: bool = True,
) -> dict[str, Any]:
    """Add or remove `eulr-refining-mcp` and `eulr-*-gcp` skills without touching Brazil entries."""
    config_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = config_dir / "mcp_config.json"
    data: dict[str, Any] = {}
    if mcp_path.is_file():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
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

    if mcp_path.is_file() or config_dir.name in {"config", "jetski", "antigravity", "cowork_workspace", ".cowork"}:
        data["mcpServers"] = servers
        mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    manifests_updated = _sync_skill_manifest_if_present(config_dir, enable=enable)
    return {
        "config_dir": str(config_dir),
        "enabled": enable,
        "mcp_servers_present": sorted(servers.keys()),
        "skills_installed": list(SKILL_IDS) if enable else [],
        "manifests_updated": manifests_updated,
    }


def resolve_default_cowork_dirs(home: Path | None = None) -> list[Path]:
    """Discover `~/.gemini/config`, `~/.gemini/jetski`, `~/cowork_workspace`, plus any home config dir already holding `brazil-bqml-gcp`."""
    base = (home or Path.home()).expanduser().resolve()
    targets: list[Path] = [base / ".gemini" / "config"]
    candidates = [
        base / ".gemini" / "jetski",
        base / "cowork_workspace",
        base / ".gemini" / "antigravity",
        base / ".cowork",
        base / ".coworkagent",
    ]
    for extra in candidates:
        if extra.is_dir() and extra not in targets:
            targets.append(extra)

    # Also auto-discover any dot-config / cowork runtime dir under ~ that already holds Installed `brazil-bqml-gcp`
    skip_roots = {"Documents", "Desktop", "Downloads", "Library", ".cache", ".local", ".git", ".venv", ".venv-linux"}
    for root_child in base.iterdir():
        if not root_child.is_dir() or root_child.name in skip_roots:
            continue
        if not (root_child.name.startswith(".") or "cowork" in root_child.name.lower() or "gemini" in root_child.name.lower()):
            continue
        try:
            for marker in root_child.glob("**/skills/brazil-bqml-gcp/SKILL.md"):
                # marker is <config_dir>/skills/brazil-bqml-gcp/SKILL.md -> parents[2] is <config_dir>
                cfg_parent = marker.parents[2].resolve()
                if cfg_parent != TWIN_ROOT.parent and cfg_parent not in targets and "eulr-bq-twin" not in str(cfg_parent) and "brazil-power-bq-twin" not in str(cfg_parent):
                    targets.append(cfg_parent)
        except Exception:
            continue
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Wire isolated EULR Digital Twin into Cowork (Mac & Cloudtop)")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Optional explicit config dir; when omitted, syncs all active Gemini/Jetski/Cowork directories.",
    )
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SSE_URL,
        help="Full /mcp/sse URL of eulr-bq-twin-mcp",
    )
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()

    if args.config_dir is not None:
        out: Any = configure_eulr_twin_in_cowork(
            config_dir=args.config_dir.expanduser().resolve(),
            server_sse_url=args.server_url,
            enable=not args.disable,
        )
    else:
        results: list[dict[str, Any]] = []
        for idx, target in enumerate(resolve_default_cowork_dirs()):
            try:
                results.append(
                    configure_eulr_twin_in_cowork(
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
