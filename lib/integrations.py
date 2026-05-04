#!/usr/bin/env python3
"""
VibeCheck integrations.

Detects and uses other tools when present:
  - graphify       (graphify-out/) — structural code graph
  - openspec       (openspec/)     — specs and project intent
  - claude-mem     (.claude-mem/)  — persistent session memory
  - icm            (~/.icm/)       — agent memory store

All integrations are optional. VibeCheck works fine without any of them.
When present, VibeCheck uses their data instead of duplicating work.

Each integration exposes a uniform API:
  - is_present(cwd)   → bool
  - get_summary(cwd)  → dict | None
  - get_relevant_for(cwd, files) → dict | None  (context for changed files)
"""

import json
from pathlib import Path
from typing import Optional, Dict, List


# ─── Detection ────────────────────────────────────────────────────────────────

def detect_all(cwd: Path) -> Dict[str, bool]:
    """Return a dict of {tool_name: is_present}."""
    return {
        "graphify": graphify_present(cwd),
        "openspec": openspec_present(cwd),
        "claude_mem": claude_mem_present(cwd),
        "icm": icm_present(cwd),
    }


def get_active_integrations(cwd: Path) -> List[str]:
    """List of integration names that are present and have data."""
    return [name for name, present in detect_all(cwd).items() if present]


# ─── Graphify ────────────────────────────────────────────────────────────────

def graphify_present(cwd: Path) -> bool:
    """Check for graphify output."""
    return (cwd / "graphify-out").is_dir() and (cwd / "graphify-out" / "graph.json").exists()


def graphify_get_summary(cwd: Path) -> Optional[Dict]:
    """High-level summary of the graphify graph."""
    graph_path = cwd / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return None
    try:
        graph = json.loads(graph_path.read_text())
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "communities": graph.get("communities", []),
            "available": True,
        }
    except Exception:
        return None


def graphify_blast_radius(cwd: Path, changed_files: List[Path]) -> List[str]:
    """
    Use graphify graph to find the blast radius (files affected by changes).
    Returns list of file paths likely to be impacted by changes to changed_files.
    """
    graph_path = cwd / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return []

    try:
        graph = json.loads(graph_path.read_text())
    except Exception:
        return []

    # Build adjacency: file → files that depend on it
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    reverse_deps = {}  # file → list of files importing it

    for edge in graph.get("edges", []):
        src = edge.get("source")
        tgt = edge.get("target")
        edge_type = edge.get("type", "")
        # Common edge types in graphify: imports, calls, references
        if edge_type in ("imports", "calls", "references", "uses"):
            reverse_deps.setdefault(tgt, []).append(src)

    # For each changed file, find its dependents (BFS, max depth 2)
    affected = set()
    changed_str = {str(f) for f in changed_files}

    for changed in changed_str:
        # Match by file path in node IDs
        for node_id, node in nodes.items():
            node_file = node.get("file", node_id)
            if node_file == changed or node_file.endswith(changed.split("/")[-1]):
                # BFS to find dependents
                queue = [(node_id, 0)]
                visited = set()
                while queue:
                    current, depth = queue.pop(0)
                    if current in visited or depth > 2:
                        continue
                    visited.add(current)
                    if current != node_id:
                        current_file = nodes.get(current, {}).get("file", current)
                        affected.add(current_file)
                    for dep in reverse_deps.get(current, []):
                        queue.append((dep, depth + 1))

    return sorted(affected)


def graphify_get_communities(cwd: Path, file_path: str) -> List[str]:
    """Get the community/cluster a file belongs to (e.g. 'auth', 'payments')."""
    graph_path = cwd / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return []
    try:
        graph = json.loads(graph_path.read_text())
        for node in graph.get("nodes", []):
            if node.get("file") == file_path:
                return node.get("communities", [])
    except Exception:
        pass
    return []


# ─── OpenSpec ────────────────────────────────────────────────────────────────

def openspec_present(cwd: Path) -> bool:
    """Check for openspec directory with at least one spec."""
    spec_dir = cwd / "openspec"
    if not spec_dir.is_dir():
        return False
    # Check it has actual content
    return any(spec_dir.glob("specs/**/*.md")) or any(spec_dir.glob("changes/**/*.md"))


def openspec_get_summary(cwd: Path) -> Optional[Dict]:
    """Summary of openspec content."""
    spec_dir = cwd / "openspec"
    if not openspec_present(cwd):
        return None

    specs = list(spec_dir.glob("specs/**/*.md"))
    changes = list(spec_dir.glob("changes/**/*.md"))
    archived = list(spec_dir.glob("changes/archive/**/*.md"))

    # Read project.md if it exists
    project_md = spec_dir / "project.md"
    project_intent = ""
    if project_md.exists():
        try:
            project_intent = project_md.read_text()[:2000]  # cap at 2KB
        except Exception:
            pass

    return {
        "spec_count": len(specs),
        "active_changes": len(changes) - len(archived),
        "archived_changes": len(archived),
        "project_intent": project_intent,
        "available": True,
    }


def openspec_get_active_changes(cwd: Path) -> List[Dict]:
    """List active (non-archived) openspec changes with their proposals."""
    spec_dir = cwd / "openspec"
    if not openspec_present(cwd):
        return []

    changes = []
    for change_dir in (spec_dir / "changes").iterdir() if (spec_dir / "changes").exists() else []:
        if not change_dir.is_dir() or change_dir.name == "archive":
            continue
        proposal_md = change_dir / "proposal.md"
        if not proposal_md.exists():
            continue
        try:
            content = proposal_md.read_text()
            # Extract first heading and first paragraph
            lines = content.strip().split("\n")
            title = lines[0].lstrip("# ").strip() if lines else change_dir.name
            description = ""
            for line in lines[1:]:
                if line.strip() and not line.startswith("#"):
                    description = line.strip()
                    break
            changes.append({
                "name": change_dir.name,
                "title": title,
                "description": description[:200],
                "path": str(proposal_md),
            })
        except Exception:
            continue
    return changes


def openspec_get_specs_for_files(cwd: Path, files: List[Path]) -> List[Dict]:
    """
    Find specs that relate to changed files.
    Heuristic: spec name or content references the file or its directory.
    """
    spec_dir = cwd / "openspec" / "specs"
    if not spec_dir.exists():
        return []

    file_keywords = set()
    for f in files:
        # Use directory names and stems as keywords
        for part in f.parts:
            if part not in {".", "src", "lib", "app"} and len(part) > 2:
                file_keywords.add(part.lower().replace(".js", "").replace(".ts", "").replace(".py", ""))
        file_keywords.add(f.stem.lower())

    relevant = []
    for spec_md in spec_dir.glob("**/*.md"):
        try:
            content = spec_md.read_text().lower()
            spec_name = spec_md.stem.lower()
            # Match if spec name or content references any keyword
            if any(kw in content or kw in spec_name for kw in file_keywords if len(kw) > 3):
                # Get first heading
                first_line = ""
                try:
                    first_line = spec_md.read_text().strip().split("\n")[0].lstrip("# ").strip()
                except Exception:
                    pass
                relevant.append({
                    "name": spec_md.stem,
                    "title": first_line or spec_md.stem,
                    "path": str(spec_md),
                })
        except Exception:
            continue

    return relevant[:5]  # cap at 5 most relevant


# ─── claude-mem ──────────────────────────────────────────────────────────────

def claude_mem_present(cwd: Path) -> bool:
    """Check for claude-mem installation."""
    candidates = [
        cwd / ".claude-mem",
        cwd / ".claude" / "claude-mem",
        Path.home() / ".claude-mem",
    ]
    return any(c.exists() for c in candidates)


def claude_mem_get_recent_context(cwd: Path) -> Optional[str]:
    """Read recent compressed context from claude-mem if available."""
    candidates = [
        cwd / ".claude-mem" / "memory.md",
        cwd / ".claude" / "claude-mem" / "memory.md",
        Path.home() / ".claude-mem" / f"{cwd.name}.md",
    ]
    for c in candidates:
        if c.exists():
            try:
                # Cap at 4KB — we just want context, not everything
                return c.read_text()[:4000]
            except Exception:
                continue
    return None


# ─── ICM ──────────────────────────────────────────────────────────────────────

def icm_present(cwd: Path) -> bool:
    """Check for icm installation."""
    return (Path.home() / ".icm").exists() or (cwd / ".icm").exists()


def icm_get_summary(cwd: Path) -> Optional[Dict]:
    """Best-effort: check ICM has any data for this project."""
    icm_dir = Path.home() / ".icm"
    if not icm_dir.exists():
        return None
    # ICM uses sqlite — we don't read it directly, just note it's available
    return {"available": True, "note": "ICM memory available (read via MCP)"}


# ─── Combined context for analyzer ───────────────────────────────────────────

def build_integration_context(cwd: Path, changed_files: List[Path]) -> Dict:
    """
    Build a dict of all available integration data for the analyzer.
    The analyzer reads this from a file rather than calling tools.
    Cheap — no LLM calls, just file reads.
    """
    context = {
        "active_integrations": get_active_integrations(cwd),
    }

    # Graphify — blast radius
    if graphify_present(cwd):
        blast = graphify_blast_radius(cwd, changed_files)
        if blast:
            context["graphify_affected_files"] = blast[:30]  # cap
        summary = graphify_get_summary(cwd)
        if summary:
            context["graphify_summary"] = summary

    # OpenSpec — relevant specs and active changes
    if openspec_present(cwd):
        active = openspec_get_active_changes(cwd)
        if active:
            context["openspec_active_changes"] = active
        relevant = openspec_get_specs_for_files(cwd, changed_files)
        if relevant:
            context["openspec_relevant_specs"] = relevant
        summary = openspec_get_summary(cwd)
        if summary:
            context["openspec_summary"] = {
                k: v for k, v in summary.items() if k != "project_intent"
            }
            # Project intent gets its own field, may be longer
            if summary.get("project_intent"):
                context["openspec_project_intent"] = summary["project_intent"][:1000]

    # Claude-mem — recent context
    if claude_mem_present(cwd):
        recent = claude_mem_get_recent_context(cwd)
        if recent:
            context["claude_mem_recent"] = recent[:2000]

    return context
