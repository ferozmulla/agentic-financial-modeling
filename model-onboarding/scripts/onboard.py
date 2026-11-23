#!/usr/bin/env python3
"""Zero-install CLI wrapper for `model_onboarding.cli:main` using the workspace `.venv`."""

from __future__ import annotations

import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PKG_ROOT.parent

for extra in (PKG_ROOT / "src", REPO_ROOT / "portfolio-assessment" / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from model_onboarding.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
