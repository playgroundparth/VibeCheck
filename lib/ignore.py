#!/usr/bin/env python3
"""
VibeCheck ignore patterns.

Reads .vibeguardignore (if present) and merges with sensible defaults.
Used by project_map (skip during indexing) and file_selection (skip during analysis).

Format is gitignore-like:
  # comments
  node_modules/        # directory
  *.min.js             # glob
  docs/                # subdirectory
  !docs/architecture.md  # negation (exception to rule above)

Defaults (always applied unless overridden):
  node_modules/, .git/, dist/, build/, .next/, __pycache__/,
  .venv/, venv/, env/, vendor/, target/, .vibeguard/,
  graphify-out/, .claude-mem/, .pytest_cache/, .mypy_cache/,
  coverage/, .nyc_output/, .turbo/, .cache/,
  *.lock, *.min.js, *.min.css, *.map
"""

import re
from pathlib import Path
from typing import List, Optional


# Always-skip patterns — never read, never index, no override.
ALWAYS_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".vibeguard",
}

# Default skip patterns — overrideable via .vibeguardignore with `!pattern`
DEFAULT_PATTERNS = [
    # Build artifacts
    "dist/", "build/", ".next/", ".nuxt/", ".turbo/", ".cache/",
    "out/", "target/", "coverage/", ".nyc_output/",

    # Virtual environments
    ".venv/", "venv/", "env/", "vendor/",

    # Tool artifacts
    ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
    "graphify-out/", ".claude-mem/",

    # Generated files
    "*.lock", "*.min.js", "*.min.css", "*.map",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "Cargo.lock", "poetry.lock", "Pipfile.lock",

    # Docs are intentionally NOT in defaults — they often have important info
    # (api docs, schema docs, etc). Users add docs/ to .vibeguardignore if they want.

    # Common large/binary patterns
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.svg",
    "*.woff", "*.woff2", "*.ttf", "*.eot",
    "*.mp4", "*.mp3", "*.pdf", "*.zip",
]


class IgnoreMatcher:
    """
    Matches paths against gitignore-style patterns.
    Built from defaults + project's .vibeguardignore (if present).
    """

    def __init__(self, cwd: Path):
        self.cwd = cwd
        self.patterns: List[tuple] = []  # list of (pattern_regex, is_negation, original_pattern)
        self._load()

    def _load(self):
        # Apply defaults first
        for p in DEFAULT_PATTERNS:
            self._add(p, is_negation=False)

        # Apply user overrides from .vibeguardignore
        ignore_file = self.cwd / ".vibeguardignore"
        if ignore_file.exists():
            try:
                content = ignore_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("!"):
                        self._add(line[1:], is_negation=True)
                    else:
                        self._add(line, is_negation=False)
            except Exception:
                pass

    def _add(self, pattern: str, is_negation: bool):
        regex = self._pattern_to_regex(pattern)
        if regex:
            self.patterns.append((regex, is_negation, pattern))

    def _pattern_to_regex(self, pattern: str) -> Optional[re.Pattern]:
        """Convert gitignore-style pattern to compiled regex."""
        if not pattern:
            return None

        # Strip leading slash (means "at root")
        anchored_at_root = pattern.startswith("/")
        if anchored_at_root:
            pattern = pattern[1:]

        # Trailing slash means "directory"
        is_dir = pattern.endswith("/")
        if is_dir:
            pattern = pattern[:-1]

        # Escape regex metas except *, ?, []
        escaped = ""
        i = 0
        while i < len(pattern):
            c = pattern[i]
            if c == "*":
                # ** = match anything including /
                # *  = match anything except /
                if i + 1 < len(pattern) and pattern[i+1] == "*":
                    escaped += ".*"
                    i += 2
                    continue
                escaped += "[^/]*"
            elif c == "?":
                escaped += "[^/]"
            elif c in ".+()^$|{}\\":
                escaped += "\\" + c
            else:
                escaped += c
            i += 1

        # Build the final regex
        if anchored_at_root:
            regex_str = f"^{escaped}"
        else:
            # Match at any depth
            regex_str = f"(^|/){escaped}"

        if is_dir:
            regex_str += f"(/|$)"
        else:
            regex_str += f"$"

        try:
            return re.compile(regex_str)
        except re.error:
            return None

    def is_ignored(self, path: Path) -> bool:
        """Check if path should be ignored."""
        # Always-skip dirs are non-overrideable
        if any(part in ALWAYS_SKIP_DIRS for part in path.parts):
            return True

        # Get path relative to project root, with forward slashes
        try:
            rel = path.relative_to(self.cwd)
        except ValueError:
            rel = path
        rel_str = str(rel).replace("\\", "/")

        # Walk through patterns in order. Last match wins.
        ignored = False
        for regex, is_negation, _orig in self.patterns:
            if regex.search(rel_str):
                ignored = not is_negation

        return ignored


# Default content for .vibeguardignore on init
DEFAULT_VIBEGUARDIGNORE_CONTENT = """# VibeCheck ignore patterns
# Like .gitignore — patterns to skip during analysis.
# Defaults are applied automatically (node_modules/, dist/, etc).
# This file is for your project-specific overrides.

# Examples:
# docs/                    # skip the entire docs directory
# *.generated.ts           # skip auto-generated TypeScript
# scripts/migrations/      # skip migration scripts
# !docs/architecture.md    # but DO analyze this specific file (negation)
# legacy/                  # skip legacy code we're not actively touching
"""
