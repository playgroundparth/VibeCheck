#!/usr/bin/env python3
"""
VibeCheck capability tier detection.

Three tiers:
  basic    — regex only, zero dependencies (always available)
  enhanced — basic + Semgrep (AST-confirmed detection)
  pro      — enhanced + Gitleaks or Graphify (secrets scanning + graph analysis)

Used by:
  - hooks/post_tool.py: decides whether to launch async detection subprocess
  - bin/doctor.js: reports current tier to user
"""

import shutil
from pathlib import Path
from typing import Optional


def detect_tier(cwd: Optional[Path] = None) -> str:
    """
    Returns 'basic', 'enhanced', or 'pro'.
    Does not throw — any detection failure falls back to 'basic'.
    """
    try:
        has_semgrep = shutil.which("semgrep") is not None
        has_gitleaks = shutil.which("gitleaks") is not None
        has_graphify = bool(cwd and (cwd / "graphify-out" / "graph.json").exists())

        if has_semgrep and (has_gitleaks or has_graphify):
            return "pro"
        elif has_semgrep:
            return "enhanced"
        return "basic"
    except Exception:
        return "basic"


def tier_summary(tier: str) -> str:
    return {
        "basic":    "Basic (regex only, zero deps)",
        "enhanced": "Enhanced (regex + Semgrep AST analysis)",
        "pro":      "Pro (regex + Semgrep + Gitleaks/Graphify)",
    }.get(tier, tier)


def missing_for_enhanced() -> list:
    """Return install hints for tools needed to reach Enhanced tier."""
    missing = []
    if not shutil.which("semgrep"):
        missing.append("semgrep — install: pip install semgrep")
    return missing


def missing_for_pro(cwd: Optional[Path] = None) -> list:
    """Return install hints for tools needed to reach Pro tier."""
    missing = list(missing_for_enhanced())
    if not shutil.which("gitleaks"):
        missing.append("gitleaks — install: brew install gitleaks")
    if cwd and not (cwd / "graphify-out" / "graph.json").exists():
        missing.append("graphify-out/graph.json — run graphify at graphify.net/")
    return missing
