#!/usr/bin/env python3
"""
VibeCheck file selection — tiered strategy.

Selects the right files for the LLM analyzer to read, scaling with project size:

  Tier 1: Always read all changed files in full (the actual diff)
  Tier 2: For each changed file, read its blast radius (files that depend on it)
          - Uses graphify graph if present (best signal)
          - Falls back to VibeCheck's project_map (lightweight, no LLM)
          - Falls back to direct-imports parsing (worst case)
  Tier 3: Project config files (package.json, pyproject.toml, etc.)
  Tier 4: Test files for changed source

Each tier is bounded by remaining token budget. The budget is dynamic:
  - Default: 30K tokens (~$0.025 on Haiku)
  - Large repos with high blast radius: up to 80K tokens
  - Small repos: 30K is plenty

The analyzer can ALSO request additional reads via session_files_addendum.txt
during analysis (iterative reading) — bounded by absolute max budget.
"""

import re
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional

import integrations
import project_map
import ignore as ignore_lib

DEFAULT_TOKEN_BUDGET = 30_000
MAX_TOKEN_BUDGET = 80_000
MAX_FILE_TOKENS = 8_000
CHARS_PER_TOKEN = 4

# These are usually small but very high-signal — always include if present
PROJECT_CONFIG_FILES = [
    "package.json", "tsconfig.json", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json",
    ".env.example", "next.config.js", "next.config.ts", "vite.config.js",
    "vite.config.ts", "astro.config.mjs",
]


def estimate_tokens(content: str) -> int:
    return max(1, len(content) // CHARS_PER_TOKEN)


def estimate_file_tokens(path: Path) -> int:
    try:
        return max(1, path.stat().st_size // CHARS_PER_TOKEN)
    except Exception:
        return 0


def select_files_to_read(
    cwd: Path,
    changed_files: List[Path],
    token_budget: Optional[int] = None,
) -> Tuple[List[Path], Dict]:
    """
    Tiered file selection scaled to project complexity.
    Returns (files, metadata).
    """
    matcher = ignore_lib.IgnoreMatcher(cwd)

    # Filter ignored files from changed list
    changed_files = [f for f in changed_files if not matcher.is_ignored(f)]

    selected: List[Path] = []
    selected_set: Set[Path] = set()
    tokens_used = 0
    skipped: List[Dict] = []

    # ── Detect available integrations ───────────────────────────────────────
    active = integrations.get_active_integrations(cwd)
    has_graphify = "graphify" in active

    # ── Determine budget based on project size ──────────────────────────────
    if token_budget is None:
        token_budget = compute_dynamic_budget(cwd, changed_files)

    # ── Tier 1: Changed files (always — even if over budget) ────────────────
    for f in changed_files:
        if not f.exists():
            continue
        size = estimate_file_tokens(f)
        if size > MAX_FILE_TOKENS:
            skipped.append({
                "file": str(f),
                "reason": "single_file_too_large",
                "tokens": size,
            })
            continue
        selected.append(f)
        selected_set.add(f)
        tokens_used += size

    # ── Tier 2: Blast radius via best available method ──────────────────────
    blast_files = []
    blast_source = "none"

    if has_graphify:
        blast_files = integrations.graphify_blast_radius(cwd, changed_files)
        blast_source = "graphify"
    elif project_map.load_map(cwd):
        blast_files = project_map.blast_radius(cwd, changed_files)
        blast_source = "project_map"
    else:
        # Fallback: direct imports parsing (one level only)
        blast_files = [str(p) for p in find_direct_imports(cwd, changed_files)]
        blast_source = "direct_imports"

    for path_str in blast_files:
        if tokens_used >= token_budget:
            break
        f = Path(path_str) if Path(path_str).is_absolute() else cwd / path_str
        if f in selected_set or not f.exists():
            continue
        if matcher.is_ignored(f):
            continue
        size = estimate_file_tokens(f)
        if size > MAX_FILE_TOKENS:
            continue
        if tokens_used + size > token_budget:
            continue
        selected.append(f)
        selected_set.add(f)
        tokens_used += size

    # ── Tier 3: Test files for changed source ───────────────────────────────
    if tokens_used < token_budget:
        for f in find_test_files_for(cwd, changed_files):
            if f in selected_set or not f.exists():
                continue
            size = estimate_file_tokens(f)
            if size > MAX_FILE_TOKENS:
                continue
            if tokens_used + size > token_budget:
                continue
            selected.append(f)
            selected_set.add(f)
            tokens_used += size

    # ── Tier 4: Project config (always small) ───────────────────────────────
    for name in PROJECT_CONFIG_FILES:
        f = cwd / name
        if f in selected_set or not f.exists():
            continue
        size = estimate_file_tokens(f)
        if tokens_used + size > token_budget:
            continue
        selected.append(f)
        selected_set.add(f)
        tokens_used += size

    metadata = {
        "tokens_used": tokens_used,
        "tokens_budgeted": token_budget,
        "files_selected": len(selected),
        "files_changed": len(changed_files),
        "blast_radius_size": len(blast_files),
        "blast_source": blast_source,
        "active_integrations": active,
        "skipped": skipped,
        "strategy": _strategy_label(changed_files, selected, tokens_used, token_budget),
    }

    return selected, metadata


def compute_dynamic_budget(cwd: Path, changed_files: List[Path]) -> int:
    """
    Scale budget based on project complexity and blast radius size.
    Small project + small change → 30K
    Large project + wide blast radius → up to 80K
    """
    map_data = project_map.load_map(cwd)
    if not map_data:
        return DEFAULT_TOKEN_BUDGET

    file_count = len(map_data.get("files", {}))

    # Small project — default budget is plenty
    if file_count < 50:
        return DEFAULT_TOKEN_BUDGET

    # Estimate blast radius size to decide
    blast_size = len(project_map.blast_radius(cwd, changed_files))

    # Scale: tiny blast = default, huge blast = up to max
    if blast_size <= 5:
        return DEFAULT_TOKEN_BUDGET
    elif blast_size <= 15:
        return min(MAX_TOKEN_BUDGET, int(DEFAULT_TOKEN_BUDGET * 1.5))
    elif blast_size <= 30:
        return min(MAX_TOKEN_BUDGET, int(DEFAULT_TOKEN_BUDGET * 2))
    else:
        return MAX_TOKEN_BUDGET


# ─── Direct imports (fallback when no map exists) ────────────────────────────

def find_direct_imports(cwd: Path, source_files: List[Path]) -> List[Path]:
    """Parse imports from source files. Resolve relative paths."""
    imported: List[Path] = []
    seen: Set[Path] = set()

    for src in source_files:
        if not src.exists():
            continue
        try:
            content = src.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        ext = src.suffix
        for imp in _extract_imports(content, ext):
            resolved = _resolve_import(cwd, src.parent, imp, ext)
            if resolved and resolved.exists() and resolved not in seen:
                imported.append(resolved)
                seen.add(resolved)

    return imported


def _extract_imports(content: str, ext: str) -> List[str]:
    imports = []
    if ext in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}:
        for m in re.finditer(r'^\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content, re.MULTILINE):
            imports.append(m.group(1))
        for m in re.finditer(r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', content):
            imports.append(m.group(1))
    elif ext == ".py":
        for m in re.finditer(r'^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))', content, re.MULTILINE):
            module = m.group(1) or m.group(2)
            imports.append(module.split(".")[0])
    elif ext == ".go":
        for m in re.finditer(r'import\s+[\'"]([^\'"]+)[\'"]', content):
            imports.append(m.group(1))
    return imports


def _resolve_import(project_root: Path, file_dir: Path, import_path: str, source_ext: str) -> Optional[Path]:
    if not import_path.startswith(".") and not import_path.startswith("/"):
        return None

    if import_path.startswith("./") or import_path.startswith("../"):
        candidate = (file_dir / import_path).resolve()
    elif import_path.startswith("/"):
        candidate = (project_root / import_path.lstrip("/")).resolve()
    else:
        candidate = (file_dir / import_path).resolve()

    if candidate.exists() and candidate.is_file():
        return candidate

    for ext in (source_ext, ".js", ".ts", ".jsx", ".tsx", ".py"):
        with_ext = Path(str(candidate) + ext)
        if with_ext.exists():
            return with_ext

    if candidate.is_dir():
        for index in ("index.ts", "index.tsx", "index.js", "index.jsx", "__init__.py"):
            idx = candidate / index
            if idx.exists():
                return idx

    return None


def find_test_files_for(cwd: Path, source_files: List[Path]) -> List[Path]:
    tests = []
    for src in source_files:
        stem = src.stem
        candidates = [
            src.parent / f"{stem}.test{src.suffix}",
            src.parent / f"{stem}.spec{src.suffix}",
            src.parent / "__tests__" / f"{stem}.test{src.suffix}",
            src.parent / "__tests__" / f"{stem}.spec{src.suffix}",
            cwd / "tests" / f"test_{stem}.py",
            cwd / "test" / f"{stem}.test{src.suffix}",
        ]
        for c in candidates:
            if c.exists() and c not in tests:
                tests.append(c)
    return tests


def _strategy_label(changed: List[Path], selected: List[Path], used: int, budget: int) -> str:
    if used > budget * 0.95:
        return "trimmed"
    elif len(selected) > len(changed):
        return "changed_plus_blast_radius"
    else:
        return "all_changed"
