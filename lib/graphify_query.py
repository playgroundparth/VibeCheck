"""
VibeCheck graphify integration.

Reads graphify-out/graph.json and extracts actionable file lists
for the scanner to use in Phase 0.

Resilient to graphify schema changes:
- Tries multiple key names for nodes/edges/labels/paths
- Falls back gracefully at every step
- Outputs plain text the scanner can act on directly

Usage:
    python3 graphify_query.py [graph_dir]
    # graph_dir defaults to ./graphify-out

Output sections (all optional — silently omitted if nothing found):
    === GRAPHIFY: Files that call security-critical functions ===
    === GRAPHIFY: Dead exports (no callers) ===
    === GRAPHIFY: Architectural hotspots (most depended-on files) ===
    === GRAPHIFY: Test coverage gaps (source files with no test caller) ===
    === GRAPHIFY: High-edge nodes (god-file candidates) ===
"""
import json
import subprocess
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict


# ── Schema resilience helpers ─────────────────────────────────────────────────

def get(obj, *keys, default=None):
    """Try multiple key names, return first match."""
    for k in keys:
        if k in obj:
            return obj[k]
    return default


def node_label(n):
    return get(n, "label", "name", "title", "norm_label", default="")


def node_file(n):
    return get(n, "source_file", "file", "path", default="")


def edge_source(e):
    return get(e, "source", "_src", "from", default="")


def edge_target(e):
    return get(e, "target", "_tgt", "to", default="")


def edge_relation(e):
    return get(e, "relation", "type", "kind", default="")


def edge_confidence(e):
    score = get(e, "confidence_score", "weight", "score", default=1.0)
    label = get(e, "confidence", "extracted", default="EXTRACTED")
    return score, label


# ── Keywords for categorization ───────────────────────────────────────────────

SECURITY_KEYWORDS = {
    "verify", "sign", "auth", "session", "token", "secret", "key", "hmac",
    "crypto", "encrypt", "decrypt", "password", "credential", "permission",
    "policy", "webhook", "signature", "jwt", "oauth", "rbac", "guard",
    "sanitize", "validate", "redact", "sensitive"
}

CALL_RELATIONS = {"calls", "imports_from", "references", "uses"}


SKIP_PATH_FRAGMENTS = {".claude/worktrees", "node_modules", "/.git/", "/dist/", "/__pycache__/"}


def is_security_node(label: str) -> bool:
    label_lower = label.lower()
    return any(kw in label_lower for kw in SECURITY_KEYWORDS)


def rel_is_call(relation: str) -> bool:
    return any(r in relation.lower() for r in CALL_RELATIONS)


def is_valid_path(path: str) -> bool:
    """Return False for paths that are worktrees, generated, or external."""
    if not path:
        return False
    return not any(frag in path for frag in SKIP_PATH_FRAGMENTS)


# ── Main extraction ───────────────────────────────────────────────────────────

def load_graph(graph_dir: Path):
    graph_path = graph_dir / "graph.json"
    if not graph_path.exists():
        return None, None, None

    with open(graph_path, encoding="utf-8", errors="replace") as f:
        g = json.load(f)

    # Nodes: try "nodes" key
    raw_nodes = get(g, "nodes", "vertices", "elements", default=[])
    nodes = {get(n, "id", "node_id", default=node_label(n)): n for n in raw_nodes if n}

    # Edges: try "links" then "edges"
    edges = get(g, "links", "edges", "connections", default=[])

    return g, nodes, edges


def extract_insights(graph_dir: Path) -> dict:
    g, nodes, edges = load_graph(graph_dir)
    if g is None:
        return {}

    # Build caller/callee maps
    # callee_id -> set of source_files that call it
    callers_of = defaultdict(set)
    # source_file -> set of callee ids
    calls_from = defaultdict(set)
    # callee_id -> call count
    call_count = Counter()
    # file -> incoming call count (from other files)
    file_in_degree = Counter()

    for e in edges:
        if not rel_is_call(edge_relation(e)):
            continue
        score, label = edge_confidence(e)
        if score < 0.5:
            continue

        src_id = edge_source(e)
        tgt_id = edge_target(e)

        src_node = nodes.get(src_id, {})
        tgt_node = nodes.get(tgt_id, {})

        src_file = node_file(src_node)
        tgt_label = node_label(tgt_node)
        tgt_file = node_file(tgt_node)

        if src_file and is_valid_path(src_file):
            callers_of[tgt_id].add(src_file)
            calls_from[src_file].add(tgt_id)
            call_count[tgt_id] += 1

        if tgt_file and is_valid_path(tgt_file) and src_file and is_valid_path(src_file) and tgt_file != src_file:
            file_in_degree[tgt_file] += 1

    results = {}

    # ── 1. Security call chains ───────────────────────────────────────────────
    # Files that call security-critical functions — read these in Phase 2p
    sec_caller_files = set()
    for nid, node in nodes.items():
        if is_security_node(node_label(node)):
            sec_caller_files.update(callers_of.get(nid, set()))

    if sec_caller_files:
        results["security_callers"] = sorted(sec_caller_files)

    # ── 2. Dead exports (no callers) ─────────────────────────────────────────
    # Nodes with no incoming call edges → DEAD_ON_ARRIVAL candidates
    # Filter to non-test, non-type files
    dead = []
    all_called_ids = set()
    for e in edges:
        if rel_is_call(edge_relation(e)):
            all_called_ids.add(edge_target(e))

    for nid, node in nodes.items():
        label = node_label(node)
        f = node_file(node)
        if not f or not label or not is_valid_path(f):
            continue
        if "test" in f.lower() or ".d.ts" in f.lower():
            continue
        if nid not in all_called_ids and call_count.get(nid, 0) == 0:
            # Only report functions/classes (not file-level nodes)
            if "." in label or "()" in label or label[0].isupper():
                dead.append((f, label))

    if dead:
        results["dead_exports"] = dead[:20]  # cap at 20

    # ── 3. Architectural hotspots (most depended-on files) ───────────────────
    # Files that many other files import — changing these has high blast radius
    if file_in_degree:
        hotspots = file_in_degree.most_common(10)
        results["hotspots"] = hotspots

    # ── 4. Test coverage gaps ─────────────────────────────────────────────────
    # Source files that no test file calls
    test_files = {n for n in calls_from if "test" in n.lower() or ".test." in n.lower()}
    test_targets = set()
    for tf in test_files:
        for nid in calls_from[tf]:
            tgt = nodes.get(nid, {})
            f = node_file(tgt)
            if f:
                test_targets.add(f)

    source_files = {
        node_file(n) for n in nodes.values()
        if node_file(n)
        and is_valid_path(node_file(n))
        and "test" not in node_file(n).lower()
        and not node_file(n).endswith(".d.ts")
        and not node_file(n).endswith(".html")
    }

    uncovered = source_files - test_targets
    # Filter to non-trivial: only files with outgoing calls (not leaf utils)
    uncovered_nontrivial = [
        f for f in uncovered
        if calls_from.get(f) and is_valid_path(f)
    ]
    if uncovered_nontrivial:
        results["test_gaps"] = sorted(uncovered_nontrivial)[:15]

    # ── 5. High-edge source files (god-file candidates) ──────────────────────
    file_out_degree = Counter()
    for e in edges:
        f = get(e, "source_file", default="")
        if f and "node_modules" not in f:
            file_out_degree[f] += 1

    if file_out_degree:
        high = [(f, c) for f, c in file_out_degree.most_common(8) if c > 15]
        if high:
            results["god_files"] = high

    return results


def format_output(results: dict, cwd: str = "") -> str:
    lines = []

    def rel(path):
        """Make path relative to cwd if possible."""
        try:
            return os.path.relpath(path, cwd) if cwd else path
        except ValueError:
            return path

    if results.get("security_callers"):
        lines.append("=== GRAPHIFY: Files calling security functions (mandatory reads for 2p) ===")
        for f in results["security_callers"]:
            lines.append(f"  {rel(f)}")

    if results.get("dead_exports"):
        lines.append("\n=== GRAPHIFY: Dead exports — no callers found (DEAD_ON_ARRIVAL candidates) ===")
        for f, label in results["dead_exports"]:
            lines.append(f"  {label}  [{rel(f)}]")

    if results.get("hotspots"):
        lines.append("\n=== GRAPHIFY: Architectural hotspots (high blast-radius if changed) ===")
        for f, count in results["hotspots"]:
            lines.append(f"  {rel(f)}  (depended on by {count} files)")

    if results.get("test_gaps"):
        lines.append("\n=== GRAPHIFY: Test coverage gaps (source files with no test caller) ===")
        for f in results["test_gaps"]:
            lines.append(f"  {rel(f)}")

    if results.get("god_files"):
        lines.append("\n=== GRAPHIFY: High-edge files (god-file candidates) ===")
        for f, count in results["god_files"]:
            lines.append(f"  {rel(f)}  ({count} outgoing edges)")

    return "\n".join(lines)


def find_repo_root() -> Path:
    """Find main repo root, works correctly from git worktrees."""
    cwd = Path.cwd()
    # --git-common-dir works from worktrees (points to shared .git dir)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if result.returncode == 0:
            git_common = result.stdout.strip()
            git_common_path = Path(git_common) if Path(git_common).is_absolute() else cwd / git_common
            root = git_common_path.resolve().parent
            if root.exists():
                return root
    except Exception:
        pass
    # Fallback: show-toplevel (fails in worktrees but ok otherwise)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except Exception:
        pass
    return cwd


def main():
    # Resolve graph_dir: explicit arg → repo root / graphify-out → parent walk
    if len(sys.argv) > 1:
        graph_dir = Path(sys.argv[1])
    else:
        repo_root = find_repo_root()
        graph_dir = repo_root / "graphify-out"

    cwd = str(find_repo_root())

    if not graph_dir.exists():
        # Last resort: walk up from CWD looking for graphify-out/
        for parent in Path.cwd().parents:
            candidate = parent / "graphify-out"
            if candidate.exists():
                graph_dir = candidate
                break
        else:
            print("graphify-out/ not found — skipping graph analysis", file=sys.stderr)
            sys.exit(0)

    try:
        results = extract_insights(graph_dir)
        if results:
            print(format_output(results, cwd))
        else:
            print("graphify: no actionable insights extracted", file=sys.stderr)
    except Exception as e:
        print(f"graphify query failed: {e}", file=sys.stderr)
        sys.exit(0)  # Non-fatal — scanner continues without graph data


if __name__ == "__main__":
    main()
