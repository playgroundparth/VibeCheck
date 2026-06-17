#!/usr/bin/env python3
"""
VibeCheck project map.

A lightweight structural index of the codebase. Built incrementally,
cached at .vibecheck/project_map.json.

For users WITH graphify installed: we use graphify's graph instead.
For users WITHOUT: this provides minimum viable structure to do
'blast radius' analysis (which files are affected by a change).

This is intentionally simpler than graphify — no LLM, no clustering,
just imports + symbols. Built in <1 second on most repos.

Schema:
{
  "files": {
    "src/auth.js": {
      "size_bytes": 4523,
      "imports": ["./db.js", "express"],
      "exports": ["login", "verify"],
      "tokens_estimated": 1130,
      "last_modified": 1714838400.0,
      "hash": "sha256_first_16_chars"
    }
  },
  "reverse_deps": {
    "src/db.js": ["src/auth.js", "src/api/users.js"]
  },
  "last_built": "2026-05-04T...",
  "version": 1
}
"""

import json
import re
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Set, Optional

import store
import ignore as ignore_lib


MAP_VERSION = 1
MAP_PATH_FRAG = "project_map.json"

# Files to scan
SOURCE_EXTENSIONS = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".rb"}

# Per-file size cap (skip huge files)
MAX_FILE_BYTES = 500_000


def map_path(cwd: Path) -> Path:
    return store.vc_dir(cwd) / MAP_PATH_FRAG


def load_map(cwd: Path) -> Optional[Dict]:
    p = map_path(cwd)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if data.get("version") != MAP_VERSION:
            return None  # stale schema
        return data
    except Exception:
        return None


def save_map(cwd: Path, data: Dict):
    store.write_json(map_path(cwd), data)


def build_full_map(cwd: Path) -> Dict:
    """
    Full build — scan every source file in the project.
    Run on init or when no map exists.
    Cost: pure Python, ~1-3 seconds on a 1000-file repo.
    """
    files = {}
    matcher = ignore_lib.IgnoreMatcher(cwd)

    for path in walk_source_files(cwd, matcher):
        rel = str(path.relative_to(cwd))
        info = analyze_file(path)
        if info:
            files[rel] = info

    reverse_deps = build_reverse_deps(files)

    map_data = {
        "files": files,
        "reverse_deps": reverse_deps,
        "last_built": _now_iso(),
        "version": MAP_VERSION,
    }
    save_map(cwd, map_data)
    return map_data


def update_map_for_files(cwd: Path, changed_files: List[Path]) -> Dict:
    """
    Incremental update — only re-analyze the changed files.
    Much cheaper than rebuilding from scratch.
    """
    map_data = load_map(cwd)
    if not map_data:
        return build_full_map(cwd)

    matcher = ignore_lib.IgnoreMatcher(cwd)
    files = map_data.get("files", {})

    for path in changed_files:
        if not path.exists():
            rel = str(path.relative_to(cwd)) if path.is_absolute() else str(path)
            files.pop(rel, None)
            continue
        # Skip if newly ignored
        if matcher.is_ignored(path):
            try:
                rel = str(path.relative_to(cwd))
            except ValueError:
                rel = str(path)
            files.pop(rel, None)
            continue
        try:
            rel = str(path.relative_to(cwd))
        except ValueError:
            continue
        info = analyze_file(path)
        if info:
            files[rel] = info

    map_data["files"] = files
    map_data["reverse_deps"] = build_reverse_deps(files)
    map_data["last_built"] = _now_iso()
    save_map(cwd, map_data)
    return map_data


def walk_source_files(cwd: Path, matcher: ignore_lib.IgnoreMatcher = None):
    """Yield source file paths, respecting .vibecheck-ignore."""
    if matcher is None:
        matcher = ignore_lib.IgnoreMatcher(cwd)

    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        if matcher.is_ignored(path):
            continue
        if path.suffix not in SOURCE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except Exception:
            continue
        yield path


def analyze_file(path: Path) -> Optional[Dict]:
    """Extract minimal info from a file: imports, exports, size."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    ext = path.suffix
    imports = extract_imports(content, ext)
    exports = extract_exports(content, ext)
    size = len(content.encode("utf-8"))
    h = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[:16]

    return {
        "size_bytes": size,
        "tokens_estimated": max(1, size // 4),
        "imports": imports[:50],     # cap to keep map small
        "exports": exports[:50],
        "hash": h,
        "last_modified": path.stat().st_mtime,
    }


def extract_imports(content: str, ext: str) -> List[str]:
    """Extract import paths."""
    imports = []
    if ext in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}:
        for m in re.finditer(r'(?:^|\n)\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content):
            imports.append(m.group(1))
        for m in re.finditer(r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', content):
            imports.append(m.group(1))
    elif ext == ".py":
        for m in re.finditer(r'(?:^|\n)\s*(?:from\s+(\S+)\s+import|import\s+(\S+))', content):
            module = m.group(1) or m.group(2)
            imports.append(module.split(".")[0])
    elif ext == ".go":
        for m in re.finditer(r'import\s+[\'"]([^\'"]+)[\'"]', content):
            imports.append(m.group(1))
    elif ext == ".rs":
        for m in re.finditer(r'(?:^|\n)\s*use\s+([a-zA-Z0-9_:]+)', content):
            imports.append(m.group(1).split("::")[0])

    return list(dict.fromkeys(imports))  # dedupe, preserve order


def extract_exports(content: str, ext: str) -> List[str]:
    """Extract exported/public names. Best-effort."""
    exports = []
    if ext in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}:
        # export function foo, export const foo, export class foo
        for m in re.finditer(r'\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type)\s+([A-Za-z_][A-Za-z0-9_]*)', content):
            exports.append(m.group(1))
        # export { foo, bar }
        for m in re.finditer(r'\bexport\s*\{([^}]+)\}', content):
            for name in m.group(1).split(","):
                name = name.strip().split(" as ")[0].strip()
                if name:
                    exports.append(name)
    elif ext == ".py":
        # Top-level def, class — simple regex
        for m in re.finditer(r'(?:^|\n)(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)', content):
            name = m.group(1)
            if not name.startswith("_"):
                exports.append(name)
    elif ext == ".go":
        # Capitalized = exported in Go
        for m in re.finditer(r'(?:^|\n)func\s+(?:\([^)]+\)\s+)?([A-Z][A-Za-z0-9_]*)', content):
            exports.append(m.group(1))
        for m in re.finditer(r'(?:^|\n)type\s+([A-Z][A-Za-z0-9_]*)', content):
            exports.append(m.group(1))
    elif ext == ".rs":
        for m in re.finditer(r'(?:^|\n)pub\s+(?:fn|struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)', content):
            exports.append(m.group(1))

    return list(dict.fromkeys(exports))


def build_reverse_deps(files: Dict[str, Dict]) -> Dict[str, List[str]]:
    """
    For each file, find which files import it.
    Returns {file_path: [list of files that import it]}.
    """
    reverse = {}
    file_paths = list(files.keys())

    for src_file, info in files.items():
        for imp in info.get("imports", []):
            # Try to resolve imp to an actual file in the project
            resolved = resolve_import_to_file(src_file, imp, file_paths)
            if resolved:
                reverse.setdefault(resolved, []).append(src_file)

    return reverse


def resolve_import_to_file(source: str, import_str: str, all_files: List[str]) -> Optional[str]:
    """Best-effort import resolution within the project."""
    if not import_str.startswith(".") and not import_str.startswith("/"):
        return None  # external package

    src_dir = "/".join(source.split("/")[:-1])
    target = import_str

    # Resolve relative
    if target.startswith("./"):
        target = src_dir + "/" + target[2:]
    elif target.startswith("../"):
        # Walk up
        parts = src_dir.split("/")
        while target.startswith("../"):
            parts = parts[:-1]
            target = target[3:]
        target = "/".join(parts) + "/" + target if parts else target

    target = target.lstrip("/").replace("//", "/")

    # Try direct match and with various extensions
    candidates = [
        target,
        f"{target}.js", f"{target}.ts", f"{target}.jsx", f"{target}.tsx",
        f"{target}.py", f"{target}.go", f"{target}.rs",
        f"{target}/index.js", f"{target}/index.ts",
        f"{target}/__init__.py",
    ]
    for c in candidates:
        if c in all_files:
            return c

    return None


# ─── Blast radius: which files are affected by changes? ─────────────────────

def blast_radius(cwd: Path, changed_files: List[Path], max_depth: int = 2) -> List[str]:
    """
    Find files affected by changes to changed_files.
    Returns list of file paths (relative to cwd), ordered by relevance.
    Uses reverse_deps map. BFS up to max_depth.

    If the project map doesn't exist, returns empty list (caller falls back
    to direct analysis of changed files).
    """
    map_data = load_map(cwd)
    if not map_data:
        return []

    reverse_deps = map_data.get("reverse_deps", {})
    affected = set()
    queue = []

    # Seed with the changed files (relative paths)
    for f in changed_files:
        try:
            rel = str(f.relative_to(cwd))
        except ValueError:
            rel = str(f)
        queue.append((rel, 0))

    visited = set()

    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > max_depth:
            continue
        visited.add(current)

        for dependent in reverse_deps.get(current, []):
            if dependent not in visited:
                affected.add(dependent)
                queue.append((dependent, depth + 1))

    return sorted(affected)


def get_file_summary(cwd: Path, file_path: str) -> Optional[Dict]:
    """Quick lookup of a file's exports/imports without re-reading."""
    map_data = load_map(cwd)
    if not map_data:
        return None
    return map_data.get("files", {}).get(file_path)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─── Artifact groups: lifecycle relationships between files ───────────────────
#
# Schema per group:
# {
#   "description": "...",
#   "source_glob": "commands/*.md",
#   "installed_by": ["bin/init.js"],         # must_check — PITFALL if missing
#   "removed_by":   ["bin/uninstall.js"],    # must_check — PITFALL if missing
#   "documented_in": ["README.md"],          # nice_check — HYGIENE if missing
#   "must_check": ["installed_by", "removed_by"],
#   "nice_check": ["documented_in"],
#   "confidence": "seeded|inferred|confirmed",
#   "evidence": ["human-readable note of how we know this"],
#   "times_confirmed": 0,
#   "created_at": "ISO",
#   "last_confirmed": null
# }
#
# Confidence lifecycle:
#   seeded    → set by init.js; assumed true, not yet verified
#   inferred  → VibeCheck found evidence of the relationship in code
#   confirmed → relationship verified multiple times (times_confirmed >= 2)

CONFIDENCE_LEVELS = ["seeded", "inferred", "confirmed"]

# Lifecycle relationship keys and their severity when the relationship is broken
MUST_CHECK_KEYS = {"installed_by", "removed_by", "wired_by"}
NICE_CHECK_KEYS = {"documented_in", "updated_by", "auth_checked_by", "migrations_in", "seed_in"}

# All lifecycle keys (order determines check priority)
LIFECYCLE_KEYS = (
    "installed_by", "updated_by", "removed_by",
    "documented_in", "wired_by", "auth_checked_by",
    "migrations_in", "seed_in",
)


def get_artifact_groups(cwd: Path) -> Dict:
    """Return artifact_groups from project_map.json."""
    map_data = load_map(cwd)
    if not map_data:
        return {}
    return map_data.get("artifact_groups", {})


def save_artifact_groups(cwd: Path, groups: Dict):
    """Merge artifact_groups into project_map.json without touching other fields."""
    map_data = load_map(cwd) or {
        "version": MAP_VERSION, "files": {}, "reverse_deps": {},
        "last_built": _now_iso(),
    }
    map_data["artifact_groups"] = groups
    map_data["last_built"] = _now_iso()
    save_map(cwd, map_data)


def find_artifact_group(file_path: str, groups: Dict) -> Optional[tuple]:
    """
    Given a relative file path, return (group_name, group_dict) if the file
    matches a source_glob in any artifact group. Returns (None, None) if no match.
    """
    import fnmatch
    for name, group in groups.items():
        glob = group.get("source_glob", "")
        if not glob:
            continue
        if fnmatch.fnmatch(file_path, glob) or fnmatch.fnmatch(file_path.split("/")[-1], glob.split("/")[-1]):
            return name, group
    return None, None


def lifecycle_files_for_changed(cwd: Path, changed_files: List[Path]) -> Dict[str, List[str]]:
    """
    Given a list of changed files, return the lifecycle files that should be
    checked for each changed file that matches an artifact group.

    Returns {changed_file_rel: {"group": name, "must_check": [...], "nice_check": [...], "check": [all]}}
    """
    groups = get_artifact_groups(cwd)
    if not groups:
        return {}

    result = {}
    for f in changed_files:
        try:
            rel = str(f.relative_to(cwd))
        except ValueError:
            rel = str(f)

        group_name, group = find_artifact_group(rel, groups)
        if not group_name:
            continue

        must_keys = set(group.get("must_check", list(MUST_CHECK_KEYS)))
        nice_keys = set(group.get("nice_check", list(NICE_CHECK_KEYS)))

        must_files, nice_files = [], []
        for key in LIFECYCLE_KEYS:
            files = group.get(key, [])
            if key in must_keys:
                must_files.extend(files)
            elif key in nice_keys:
                nice_files.extend(files)

        all_files = list(dict.fromkeys(must_files + nice_files))
        result[rel] = {
            "group": group_name,
            "confidence": group.get("confidence", "seeded"),
            "description": group.get("description", ""),
            "must_check": list(dict.fromkeys(must_files)),
            "nice_check": list(dict.fromkeys(nice_files)),
            "check": all_files,
        }

    return result


# ─── Self-healing: update groups based on evidence found during review ────────

def upgrade_group_confidence(cwd: Path, group_name: str, evidence_note: str) -> bool:
    """
    Promote a group's confidence one step (seeded → inferred → confirmed).
    Records evidence_note. Returns True if promoted.
    """
    groups = get_artifact_groups(cwd)
    group = groups.get(group_name)
    if not group:
        return False

    current = group.get("confidence", "seeded")
    idx = CONFIDENCE_LEVELS.index(current) if current in CONFIDENCE_LEVELS else 0
    if idx >= len(CONFIDENCE_LEVELS) - 1:
        # Already at max — still record evidence and increment times_confirmed
        group["times_confirmed"] = group.get("times_confirmed", 0) + 1
        group["last_confirmed"] = _now_iso()
        evidence = group.setdefault("evidence", [])
        if evidence_note and evidence_note not in evidence:
            evidence.append(evidence_note)
        save_artifact_groups(cwd, groups)
        return False

    group["confidence"] = CONFIDENCE_LEVELS[idx + 1]
    group["times_confirmed"] = group.get("times_confirmed", 0) + 1
    group["last_confirmed"] = _now_iso()
    evidence = group.setdefault("evidence", [])
    if evidence_note and evidence_note not in evidence:
        evidence.append(evidence_note)

    groups[group_name] = group
    save_artifact_groups(cwd, groups)
    return True


def add_inferred_group(cwd: Path, group_name: str, group_dict: Dict, evidence_note: str) -> bool:
    """
    Add a new artifact group discovered during analysis (confidence: inferred).
    Does not overwrite existing groups.
    """
    groups = get_artifact_groups(cwd)
    if group_name in groups:
        return False  # Already exists — use upgrade_group_confidence instead

    sanitized = re.sub(r'[^a-z0-9_]', '_', group_name.lower().strip())[:40] or "unknown"
    must_keys = [k for k in group_dict if k in MUST_CHECK_KEYS]
    nice_keys = [k for k in group_dict if k in NICE_CHECK_KEYS]

    new_group = {
        **group_dict,
        "confidence": "inferred",
        "must_check": must_keys,
        "nice_check": nice_keys,
        "evidence": [evidence_note] if evidence_note else [],
        "times_confirmed": 1,
        "created_at": _now_iso(),
        "last_confirmed": _now_iso(),
    }
    groups[sanitized] = new_group
    save_artifact_groups(cwd, groups)
    return True


def severity_for_missing_relationship(group: Dict, relationship_key: str) -> str:
    """
    Return the finding severity for a missing relationship.
    must_check keys → PITFALL; nice_check keys → HYGIENE or GOOD_TO_HAVE.
    """
    must_keys = set(group.get("must_check", list(MUST_CHECK_KEYS)))
    nice_keys = set(group.get("nice_check", list(NICE_CHECK_KEYS)))
    if relationship_key in must_keys:
        return "PITFALL"
    if relationship_key in nice_keys:
        return "HYGIENE"
    return "GOOD_TO_HAVE"
