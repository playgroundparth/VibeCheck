#!/usr/bin/env python3
"""
VibeCheck async detection worker.

Runs Semgrep (and optionally Gitleaks) in the background after a file edit.
Called by hooks/post_tool.py as a detached subprocess — does NOT block the hook.
Results are written to .vibecheck/async_results.json and surfaced by
session_start.py at the beginning of the next Claude Code session.

Hard constraints (enforced in code):
  max runtime:   120s per tool (subprocess timeout)
  max files:     50 (truncated before passing to tools)
  max procs:     1 concurrent (caller checks .vibecheck/async.lock before spawning)
  stale results: async_results.json older than 24h is discarded at read time
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


MAX_FILES = 50
MAX_RUNTIME_SECONDS = 120


# ── Severity mapping ──────────────────────────────────────────────────────────

def _map_semgrep_severity(s: str) -> str:
    """Map Semgrep severity labels to VibeCheck severity."""
    return {
        "ERROR":   "CRITICAL",
        "WARNING": "PITFALL",
        "INFO":    "HYGIENE",
    }.get(s.upper(), "PITFALL")


# ── Semgrep ───────────────────────────────────────────────────────────────────

def run_semgrep(cwd: Path, files: list) -> list:
    """
    Run Semgrep with auto-config, return evidence items with source='semgrep'.
    Semgrep results are always confidence='high' — AST-confirmed.
    """
    files = [f for f in files if Path(f).exists()][:MAX_FILES]
    if not files:
        return []

    cmd = [
        "semgrep",
        "--json",
        "--config=auto",
        "--no-rewrite-rule-ids",
        "--quiet",
    ] + files

    try:
        result = subprocess.run(
            cmd, cwd=cwd,
            capture_output=True, text=True,
            timeout=MAX_RUNTIME_SECONDS,
        )
        # Semgrep exits 0 (no findings) or 1 (findings) — both are OK
        if result.returncode not in (0, 1):
            return []

        data = json.loads(result.stdout)
        evidence = []
        for r in data.get("results", []):
            evidence.append({
                "pattern_id": r.get("check_id", "SEMGREP"),
                "source": "semgrep",
                "confidence": "high",   # Semgrep = AST-confirmed
                "confidence_reason": "Semgrep AST-confirmed match",
                "file": r.get("path", ""),
                "line": r.get("start", {}).get("line", 0),
                "matched_text": r.get("extra", {}).get("lines", "").strip()[:200],
                "suggested_severity": _map_semgrep_severity(
                    r.get("extra", {}).get("severity", "WARNING")
                ),
                "check_question": r.get("extra", {}).get("message", ""),
            })
        return evidence

    except subprocess.TimeoutExpired:
        return []
    except (json.JSONDecodeError, Exception):
        return []


# ── Gitleaks ──────────────────────────────────────────────────────────────────

def run_gitleaks(cwd: Path, files: list) -> list:
    """
    Run Gitleaks on the specified files, return evidence items with source='gitleaks'.
    Gitleaks exact-match = always confidence='high'.
    """
    files = [f for f in files if Path(f).exists()][:MAX_FILES]
    if not files:
        return []

    try:
        cmd = ["gitleaks", "detect", "--report-format=json", "--no-git", "--source=."]
        result = subprocess.run(
            cmd, cwd=cwd,
            capture_output=True, text=True,
            timeout=MAX_RUNTIME_SECONDS,
        )
        # Gitleaks exits 0 (clean) or 1 (findings found)
        if result.returncode not in (0, 1):
            return []

        if not result.stdout.strip():
            return []

        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return []

        evidence = []
        for r in data:
            file_path = r.get("File", "")
            # Only report on files we changed
            if not any(file_path.endswith(str(Path(f).name)) for f in files):
                continue
            evidence.append({
                "pattern_id": f"SECRET_{r.get('RuleID', 'GITLEAKS').upper().replace('-', '_')}",
                "source": "gitleaks",
                "confidence": "high",   # Gitleaks exact-match
                "confidence_reason": f"Gitleaks detected secret: {r.get('Description', '')}",
                "file": file_path,
                "line": r.get("StartLine", 0),
                "matched_text": r.get("Secret", "")[:20] + "..." if r.get("Secret") else "",
                "suggested_severity": "CRITICAL",
                "check_question": (
                    f"Is this a real secret ({r.get('Description', 'credential')}) "
                    f"hardcoded in source? Move to environment variable immediately."
                ),
            })
        return evidence

    except subprocess.TimeoutExpired:
        return []
    except (json.JSONDecodeError, Exception):
        return []


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VibeCheck async detection worker")
    parser.add_argument("--cwd", required=True, help="Project root directory")
    parser.add_argument("--files", required=True, help="Comma-separated list of changed files")
    args = parser.parse_args()

    cwd = Path(args.cwd)
    files = [f for f in args.files.split(",") if f.strip()][:MAX_FILES]
    vg_dir = cwd / ".vibecheck"

    if not vg_dir.exists():
        sys.exit(0)

    lock_path = vg_dir / "async.lock"

    # Write lock file so post_tool.py knows we're running
    try:
        lock_path.write_text(str(time.time()))
    except Exception:
        sys.exit(0)

    try:
        results = []

        # Run Semgrep if available
        import shutil
        if shutil.which("semgrep"):
            results.extend(run_semgrep(cwd, files))

        # Run Gitleaks if available
        if shutil.which("gitleaks"):
            results.extend(run_gitleaks(cwd, files))

        if results:
            out_path = vg_dir / "async_results.json"
            out_path.write_text(json.dumps({
                "results": results,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "files_analyzed": files,
            }, indent=2))

    except Exception:
        pass  # Non-fatal — next session proceeds without async results
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
