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


# ── Mutation testing ──────────────────────────────────────────────────────────
# Only runs when mutation testing IS already configured — does not bootstrap it.
# TEST-01 inline evidence handles the "not configured" case.
# Results are surfaced as structured evidence so session_start.py can show score.

MAX_MUTATION_SECONDS = 300  # 5 minutes — mutation testing is slow by design

_MUTATION_SCORE_RESULT_KEY = "mutation_score"


def _detect_mutation_config(cwd: Path) -> tuple:
    """
    Returns (tool_name, command) if mutation testing is configured, else (None, None).
    Priority: Stryker > mutmut > pitest > cargo-mutants
    """
    # Stryker (JS/TS)
    stryker_configs = [
        ".stryker.conf.js", ".stryker.conf.mjs", ".stryker.conf.cjs",
        ".stryker.conf.json", "stryker.config.js", "stryker.config.mjs",
    ]
    if any((cwd / c).exists() for c in stryker_configs):
        return ("stryker", ["npx", "stryker", "run"])

    # mutmut (Python)
    if (cwd / "mutmut.toml").exists():
        return ("mutmut", ["mutmut", "run"])
    setup_cfg = cwd / "setup.cfg"
    if setup_cfg.exists():
        try:
            if "[mutmut]" in setup_cfg.read_text(encoding="utf-8", errors="ignore"):
                return ("mutmut", ["mutmut", "run"])
        except Exception:
            pass

    # pitest (Java via Maven)
    pom = cwd / "pom.xml"
    if pom.exists():
        try:
            if "pitest" in pom.read_text(encoding="utf-8", errors="ignore"):
                return ("pitest", ["mvn", "test-compile", "org.pitest:pitest-maven:mutationCoverage"])
        except Exception:
            pass

    # cargo-mutants (Rust)
    cargo = cwd / "Cargo.toml"
    if cargo.exists():
        try:
            if "cargo-mutants" in cargo.read_text(encoding="utf-8", errors="ignore"):
                return ("cargo-mutants", ["cargo", "mutants"])
        except Exception:
            pass

    return (None, None)


def _parse_mutation_score(tool: str, stdout: str, stderr: str) -> dict:
    """
    Extract mutation score from tool output. Returns dict with score info.
    Best-effort — if parsing fails, returns raw summary.
    """
    combined = stdout + "\n" + stderr

    if tool == "stryker":
        # Stryker: "Mutation score: 72.22%"
        m = re.search(r"Mutation score[:\s]+(\d+(?:\.\d+)?)\s*%", combined, re.IGNORECASE)
        killed = re.search(r"Killed\s+(\d+)", combined)
        survived = re.search(r"Survived\s+(\d+)", combined)
        total = re.search(r"Total detected\s+(\d+)|(\d+)\s+mutant", combined)
        return {
            "score_pct": float(m.group(1)) if m else None,
            "killed": int(killed.group(1)) if killed else None,
            "survived": int(survived.group(1)) if survived else None,
        }

    elif tool == "mutmut":
        # mutmut: "🎉 All 42 mutants are killed."  or  "X out of Y mutants survived"
        survived = re.search(r"(\d+)\s+out\s+of\s+(\d+)\s+mutants?\s+survived", combined)
        all_killed = re.search(r"All\s+(\d+)\s+mutants?\s+(?:are\s+)?killed", combined)
        if survived:
            s, t = int(survived.group(1)), int(survived.group(2))
            score = round((t - s) / t * 100, 1) if t else None
            return {"score_pct": score, "killed": t - s, "survived": s}
        elif all_killed:
            t = int(all_killed.group(1))
            return {"score_pct": 100.0, "killed": t, "survived": 0}
        return {"score_pct": None, "killed": None, "survived": None}

    return {"score_pct": None, "killed": None, "survived": None}


def run_mutation_testing(cwd: Path, files: list) -> list:
    """
    Run mutation testing if configured. Returns evidence items with source='mutation'.
    Only runs when test files are in the changed set — no point running if only
    source files changed without their tests.
    """
    # Only run if any changed file is a test file
    test_exts = {".ts", ".tsx", ".js", ".jsx", ".py"}
    test_file_patterns = re.compile(
        r"\.test\.(ts|tsx|js|jsx)|\.spec\.(ts|tsx|js|jsx)|"
        r"(^|[/\\])test_[^/\\]+\.py$|[^/\\]+_test\.py$",
        re.IGNORECASE,
    )
    has_test_file = any(
        test_file_patterns.search(f) or
        (Path(f).suffix in test_exts and "test" in Path(f).name.lower())
        for f in files
    )
    if not has_test_file:
        return []

    tool, cmd = _detect_mutation_config(cwd)
    if not tool or not cmd:
        return []  # Not configured — TEST-01 inline evidence handles this

    try:
        result = subprocess.run(
            cmd, cwd=cwd,
            capture_output=True, text=True,
            timeout=MAX_MUTATION_SECONDS,
        )
        score_data = _parse_mutation_score(tool, result.stdout, result.stderr)
        score_pct = score_data.get("score_pct")
        survived = score_data.get("survived")
        killed = score_data.get("killed")

        # Build a human-readable summary for the session_start injection
        if score_pct is not None:
            if score_pct >= 80:
                verdict = f"✅ {score_pct}% mutation score — tests are catching real bugs"
                severity = "HYGIENE"
            elif score_pct >= 50:
                verdict = f"⚠️  {score_pct}% mutation score — {survived} mutants survived your test suite"
                severity = "PITFALL"
            else:
                verdict = f"❌ {score_pct}% mutation score — {survived} mutants survived, tests are not verifying correctness"
                severity = "CRITICAL"
        else:
            verdict = f"{tool} ran — check output for mutation score"
            severity = "HYGIENE"

        return [{
            "pattern_id": "TEST-01",
            "source": "mutation",
            "confidence": "high",
            "confidence_reason": f"{tool} mutation score: {score_pct}%" if score_pct is not None else f"{tool} ran",
            "file": str(files[0]) if files else "",
            "line": 0,
            "matched_text": verdict,
            "suggested_severity": severity,
            "check_question": (
                f"{tool} mutation score: {score_pct}%. "
                + (f"{survived} mutants survived — these are logic paths your tests don't cover. "
                   f"Run `{' '.join(cmd)}` then check which mutants survived to find untested behavior."
                   if survived and survived > 0 else
                   "All mutants killed — your tests are verifying real behavior.")
            ),
            # Extra fields for session_start rendering
            "mutation_score_pct": score_pct,
            "mutation_survived": survived,
            "mutation_killed": killed,
            "mutation_tool": tool,
        }]

    except subprocess.TimeoutExpired:
        return [{
            "pattern_id": "TEST-01",
            "source": "mutation",
            "confidence": "low",
            "confidence_reason": f"{tool} timed out after {MAX_MUTATION_SECONDS}s",
            "file": "",
            "line": 0,
            "matched_text": f"{tool} mutation run timed out",
            "suggested_severity": "HYGIENE",
            "check_question": f"{tool} timed out. Your test suite may be too slow for mutation testing — consider running on a subset.",
        }]
    except Exception:
        return []


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VibeCheck async detection worker")
    parser.add_argument("--cwd", required=True, help="Project root directory")
    parser.add_argument("--files", required=True, help="Comma-separated list of changed files")
    args = parser.parse_args()

    cwd = Path(args.cwd)
    files = [f for f in args.files.split(",") if f.strip()][:MAX_FILES]
    vc_dir = cwd / ".vibecheck"

    if not vc_dir.exists():
        sys.exit(0)

    lock_path = vc_dir / "async.lock"

    # Write lock file so post_tool.py knows we're running
    try:
        lock_path.write_text(str(time.time()))
    except Exception:
        sys.exit(0)

    try:
        results = []
        import shutil

        cfg = {}
        try:
            cfg_path = vc_dir / "config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
        except Exception:
            pass
        mode = cfg.get("mode", "full")

        # Run Semgrep if available (runs in full and pro modes)
        if mode in ("full", "pro") and shutil.which("semgrep"):
            results.extend(run_semgrep(cwd, files))

        # Run Gitleaks if available (only in pro mode)
        if mode == "pro" and shutil.which("gitleaks"):
            results.extend(run_gitleaks(cwd, files))

        # Run mutation testing if configured (only in pro mode)
        if mode == "pro":
            results.extend(run_mutation_testing(cwd, files))

        if results:
            out_path = vc_dir / "async_results.json"
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
