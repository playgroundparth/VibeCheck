#!/usr/bin/env python3
"""
VibeCheck project identity.

Provides a stable repo ID so memory/findings persist across:
  - Directory renames
  - Cloning to a new path
  - Multiple repos open in the same Claude Code session
  - User cd-ing into subdirectories

Strategy (in order of preference):
  1. Git remote URL (most stable)
  2. Git first commit hash (for repos with no remote)
  3. Path hash (fallback for non-git projects)

Each project also gets a human-readable "name" derived from package.json,
pyproject.toml, etc., for display purposes.

Multi-repo handling:
  - Per-project: .vibecheck/ inside each repo (data isolation)
  - Optional global registry: ~/.vibecheck/registry.json (project list only,
    no findings, no code)
"""

import json
import hashlib
import subprocess
import os
from pathlib import Path
from typing import Optional, Dict, List


GLOBAL_DIR = Path.home() / ".vibecheck"
GLOBAL_REGISTRY = GLOBAL_DIR / "registry.json"


# ─── Repo root resolution ────────────────────────────────────────────────────

def find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """
    Find the main repository root, working correctly from git worktrees.

    Git worktrees have their own 'show-toplevel' that points to the worktree
    directory, not the main repo. '--git-common-dir' always points to the
    shared .git directory of the main repo, so dirname of that is the real root.

    Strategy (in order):
      1. git rev-parse --git-common-dir  (works from worktrees — shared .git dir)
      2. git rev-parse --show-toplevel   (fallback for non-worktree repos)
      3. Walk-up looking for .vibecheck/ (fallback for non-git projects)

    Returns None if no root found.
    """
    cwd = (start or Path.cwd()).resolve()

    # Strategy 1: git-common-dir — the only reliable method from worktrees
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_common = result.stdout.strip()
            git_common_path = Path(git_common) if Path(git_common).is_absolute() else cwd / git_common
            repo_root = git_common_path.resolve().parent
            # Sanity: must exist and not be inside node_modules or similar
            if repo_root.exists() and repo_root != Path("/"):
                return repo_root
    except Exception:
        pass

    # Strategy 2: show-toplevel (fails in worktrees but fine for non-worktree)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except Exception:
        pass

    return None


def find_project_root(start: Path) -> Optional[Path]:
    """
    Find the project root — the directory containing .vibecheck/.

    Works from:
      - The main repo root
      - Any subdirectory of the repo
      - Git worktrees (inside or outside the main repo)

    Strategy:
      1. find_repo_root() to get the main git repo root — check it for .vibecheck/
      2. Walk up from start path (catches subdirectory usage)
    """
    # Fast path: git-based root is almost always correct
    repo_root = find_repo_root(start)
    if repo_root and (repo_root / ".vibecheck").is_dir():
        return repo_root

    # Walk-up fallback: catches subdirectory usage and non-git projects
    current = start.resolve()
    home = Path.home().resolve()
    fs_root = Path(current.anchor)

    while current != fs_root and current != home.parent:
        if (current / ".vibecheck").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent

    return None


# ─── Project ID and info ─────────────────────────────────────────────────────

def get_project_id(cwd: Path) -> str:
    """
    Return a stable identifier for this project.
    Cached in .vibecheck/project_id.txt at install time.
    """
    cache_path = cwd / ".vibecheck" / "project_id.txt"
    if cache_path.exists():
        try:
            cached = cache_path.read_text().strip()
            if cached:
                return cached
        except Exception:
            pass

    # Compute fresh
    pid = compute_project_id(cwd)

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(pid)
    except Exception:
        pass

    return pid


def compute_project_id(cwd: Path) -> str:
    """Compute project ID from scratch. Used at install time."""
    pid = _git_remote_id(cwd)
    if not pid:
        pid = _git_first_commit_id(cwd)
    if not pid:
        pid = _path_hash_id(cwd)
    return pid


def get_project_name(cwd: Path) -> str:
    """Best-effort human-readable project name."""
    pkg = cwd / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            if name := data.get("name"):
                return str(name)
        except Exception:
            pass

    pyproject = cwd / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("name") and "=" in line:
                    name = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if name:
                        return name
        except Exception:
            pass

    cargo = cwd / "Cargo.toml"
    if cargo.exists():
        try:
            content = cargo.read_text()
            in_package = False
            for line in content.splitlines():
                line = line.strip()
                if line == "[package]":
                    in_package = True
                    continue
                if line.startswith("[") and in_package:
                    break
                if in_package and line.startswith("name") and "=" in line:
                    name = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if name:
                        return name
        except Exception:
            pass

    return cwd.name


def get_project_info(cwd: Path) -> Dict:
    """Combined project identity info."""
    return {
        "id": get_project_id(cwd),
        "name": get_project_name(cwd),
        "path": str(cwd),
        "git_remote": _git_remote_url(cwd),
        "git_branch": _git_current_branch(cwd),
    }


# ─── Multi-repo session handling ─────────────────────────────────────────────

def detect_project_change(cwd: Path) -> Optional[Dict]:
    """
    Detect if we're now in a different project than last time the hook fired.
    Returns dict with old/new info if changed, None if same project.

    This is per-machine, not per-process — so it correctly detects when
    the user switches Claude Code from one project to another mid-session.
    """
    last_path = cwd / ".vibecheck" / "last_session_path.txt"
    current_id = get_project_id(cwd)

    if not last_path.exists():
        try:
            last_path.parent.mkdir(parents=True, exist_ok=True)
            last_path.write_text(f"{current_id}\n{cwd}")
        except Exception:
            pass
        return None

    try:
        content = last_path.read_text().strip().split("\n")
        last_id = content[0] if content else ""
        last_path_str = content[1] if len(content) > 1 else ""
    except Exception:
        return None

    if last_id != current_id:
        try:
            last_path.write_text(f"{current_id}\n{cwd}")
        except Exception:
            pass
        return {
            "changed": True,
            "previous_id": last_id,
            "previous_path": last_path_str,
            "current_id": current_id,
            "current_path": str(cwd),
        }

    return None


# ─── Global registry (optional, opt-in) ──────────────────────────────────────

def registry_load() -> Dict:
    """Load the global project registry. Returns empty dict if missing."""
    if not GLOBAL_REGISTRY.exists():
        return {"projects": {}, "version": 1}
    try:
        return json.loads(GLOBAL_REGISTRY.read_text())
    except Exception:
        return {"projects": {}, "version": 1}


def registry_save(data: Dict) -> bool:
    """Save the global registry."""
    try:
        GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
        GLOBAL_REGISTRY.write_text(json.dumps(data, indent=2))
        return True
    except Exception:
        return False


def registry_register(cwd: Path) -> Optional[str]:
    """
    Register this project in the global registry.
    Called at install time. Returns the project_id.

    Stores ONLY: project_id, name, path, git_remote, last_seen.
    NO code, NO findings, NO secrets.
    """
    info = get_project_info(cwd)
    pid = info["id"]

    registry = registry_load()
    if "projects" not in registry:
        registry["projects"] = {}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Update or insert
    if pid in registry["projects"]:
        registry["projects"][pid].update({
            "name": info["name"],
            "path": info["path"],
            "git_remote": info["git_remote"],
            "last_seen": now,
        })
    else:
        registry["projects"][pid] = {
            "id": pid,
            "name": info["name"],
            "path": info["path"],
            "git_remote": info["git_remote"],
            "first_seen": now,
            "last_seen": now,
        }

    if registry_save(registry):
        return pid
    return None


def registry_touch(cwd: Path):
    """Update last_seen for this project. Called from hooks."""
    info = get_project_info(cwd)
    pid = info["id"]
    registry = registry_load()
    if "projects" not in registry:
        return
    if pid in registry["projects"]:
        from datetime import datetime, timezone
        registry["projects"][pid]["last_seen"] = datetime.now(timezone.utc).isoformat()
        # Update path in case repo was moved
        registry["projects"][pid]["path"] = info["path"]
        registry_save(registry)


def registry_unregister(cwd: Path):
    """Remove this project from the registry. Called on uninstall."""
    pid = get_project_id(cwd)
    registry = registry_load()
    if "projects" in registry and pid in registry["projects"]:
        del registry["projects"][pid]
        registry_save(registry)


def registry_list() -> List[Dict]:
    """Return all registered projects, sorted by last_seen."""
    registry = registry_load()
    projects = list(registry.get("projects", {}).values())
    projects.sort(key=lambda p: p.get("last_seen", ""), reverse=True)
    return projects


# ─── Internal helpers ────────────────────────────────────────────────────────

def _git_remote_id(cwd: Path) -> Optional[str]:
    url = _git_remote_url(cwd)
    if not url:
        return None
    normalized = url.lower()
    for prefix in ("https://", "http://", "git@", "ssh://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.replace(":", "/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    normalized = normalized.rstrip("/")
    h = hashlib.sha1(normalized.encode()).hexdigest()[:12]
    return f"git-{h}"


def _git_remote_url(cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            return url if url else None
    except Exception:
        pass
    return None


def _git_first_commit_id(cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_commit = result.stdout.strip().split("\n")[0]
            return f"commit-{first_commit[:12]}"
    except Exception:
        pass
    return None


def _git_current_branch(cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else None
    except Exception:
        pass
    return None


def _path_hash_id(cwd: Path) -> str:
    abs_path = str(cwd.resolve())
    h = hashlib.sha1(abs_path.encode()).hexdigest()[:12]
    return f"path-{h}"
