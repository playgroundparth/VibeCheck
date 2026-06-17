#!/usr/bin/env python3
"""
VibeCheck pattern engine.

Patterns are reusable check rules. Each has:
  - A deterministic trigger (file glob + content regex) — evaluated WITHOUT LLM
  - A check question — only asked to LLM if trigger fires
  - Confidence tier — controls whether pattern is active

Lifecycle:
  candidate → low → high  (promoted by repeated successful firing)
                  ↓
  candidate ← low ← high  (demoted by false positives or staleness)
                  ↓
  killed (removed)

This prevents pattern explosion: patterns are only "created" as candidates
and only "promoted" after evidence they catch real issues.
"""

import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

# Re-use store helpers
import store

CONFIDENCE_LEVELS = ["candidate", "low", "high"]
PROMOTE_AFTER_FIRES = 3       # candidate → low → high
DEMOTE_AFTER_FALSE_POS = 2    # back down
KILL_AFTER_DEMOTIONS = 2      # gone for good
STALE_DAYS = 30               # demoted if not fired in this many days

MAX_PATTERNS_PER_RUN = 1      # analyzer can propose at most 1 new pattern per run
MAX_ACTIVE_PATTERNS = 50      # cap total patterns to prevent runaway growth


# ─── Pattern schema ──────────────────────────────────────────────────────────

PATTERN_SCHEMA_REQUIRED = {
    "name",           # snake-case identifier
    "description",    # one sentence, plain English
    "trigger",        # dict with file_glob and content_regex
    "check",          # the question for the LLM
    "severity",       # CRITICAL | PITFALL | HYGIENE | GOOD_TO_HAVE
}


def validate_pattern(pattern: dict) -> Optional[str]:
    """Return None if valid, error message if not."""
    missing = PATTERN_SCHEMA_REQUIRED - set(pattern.keys())
    if missing:
        return f"Missing required fields: {missing}"

    trigger = pattern.get("trigger", {})
    if not isinstance(trigger, dict):
        return "trigger must be a dict"
    if "file_glob" not in trigger:
        return "trigger missing file_glob"
    if "content_regex" not in trigger:
        return "trigger missing content_regex"

    # Validate regex compiles
    try:
        re.compile(trigger["content_regex"])
    except re.error as e:
        return f"content_regex is invalid: {e}"

    if pattern["severity"] not in {"CRITICAL", "PITFALL", "HYGIENE", "GOOD_TO_HAVE"}:
        return f"invalid severity: {pattern['severity']}"

    # Trigger sanity: must not match everything
    if trigger["content_regex"] in {".*", ".+", ""}:
        return "content_regex too broad — would match everything"
    if trigger["file_glob"] in {"**", "*", "**/*"}:
        return "file_glob too broad — would match every file"

    return None


# ─── Pattern proposal (called by LLM analyzer via store) ─────────────────────

def propose_pattern(cwd: Path, pattern: dict, evidence_finding_id: str) -> Optional[str]:
    """
    Called by the LLM analyzer when it sees something it thinks should become a pattern.
    Patterns are created as 'candidate' status — they don't fire yet.
    They get promoted only after the same finding type appears repeatedly.

    Returns the pattern name on success, None on rejection.
    """
    err = validate_pattern(pattern)
    if err:
        store.log_event(cwd, {
            "type": "pattern_rejected",
            "reason": err,
            "proposed_name": pattern.get("name", "unknown"),
        })
        return None

    # Check pattern count cap
    existing = load_all_patterns(cwd)
    active_count = sum(1 for p in existing if p.get("status") == "active")
    if active_count >= MAX_ACTIVE_PATTERNS:
        store.log_event(cwd, {
            "type": "pattern_rejected",
            "reason": f"max active patterns reached ({MAX_ACTIVE_PATTERNS})",
            "proposed_name": pattern["name"],
        })
        return None

    # Check duplicate
    name = sanitize_name(pattern["name"])
    if any(p.get("name") == name for p in existing):
        return None  # silently skip — pattern already exists

    # Create as candidate
    new_pattern = {
        "name": name,
        "description": pattern["description"],
        "trigger": pattern["trigger"],
        "check": pattern["check"],
        "severity": pattern["severity"],
        "confidence": "candidate",
        "status": "active",
        "times_fired": 0,
        "false_positives": 0,
        "demotions": 0,
        "evidence_findings": [evidence_finding_id],
        "created_at": now_iso(),
        "last_fired": None,
    }

    save_pattern(cwd, new_pattern)
    store.log_event(cwd, {
        "type": "pattern_created",
        "name": name,
        "confidence": "candidate",
    })
    return name


# ─── Trigger evaluation (deterministic, no LLM) ──────────────────────────────

def evaluate_triggers(cwd: Path, changed_files: List[Path]) -> List[Dict]:
    """
    Run all active patterns' triggers against changed files.
    Returns list of {pattern, matched_file, matched_line} for each fire.
    Pure Python — no LLM calls. Fast.
    """
    patterns = load_all_patterns(cwd)
    fires = []

    for pattern in patterns:
        if pattern.get("status") != "active":
            continue
        # Candidates are allowed to fire to accumulate match counts and get promoted

        trigger = pattern["trigger"]
        file_glob = trigger["file_glob"]
        content_regex = trigger["content_regex"]

        try:
            content_re = re.compile(content_regex)
        except re.error:
            continue  # broken pattern, skip silently

        for file_path in changed_files:
            if not match_glob(file_path, file_glob):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for line_num, line in enumerate(content.split("\n"), 1):
                if content_re.search(line):
                    fires.append({
                        "pattern": pattern,
                        "file": str(file_path),
                        "line": line_num,
                        "matched_text": line.strip()[:120],
                    })
                    increment_fired(cwd, pattern["name"])
                    break  # one fire per file per pattern

    return fires


def match_glob(file_path: Path, glob: str) -> bool:
    """Simple glob matcher. Supports **, *, ?."""
    # Convert to forward-slash string, relative to cwd if possible
    s = str(file_path).replace("\\", "/")

    # Translate glob to regex
    pattern = glob.replace(".", "\\.")
    pattern = pattern.replace("**", "DOUBLESTAR")
    pattern = pattern.replace("*", "[^/]*")
    pattern = pattern.replace("DOUBLESTAR", ".*")
    pattern = pattern.replace("?", ".")
    pattern = f"(^|/){pattern}$"

    try:
        return bool(re.search(pattern, s))
    except re.error:
        return False


# ─── Pattern lifecycle ───────────────────────────────────────────────────────

def increment_fired(cwd: Path, pattern_name: str):
    """Track pattern firing. Promote if threshold reached."""
    pattern = load_pattern(cwd, pattern_name)
    if not pattern:
        return

    pattern["times_fired"] = pattern.get("times_fired", 0) + 1
    pattern["last_fired"] = now_iso()

    # Promote if eligible
    fires = pattern["times_fired"]
    fp = pattern.get("false_positives", 0)
    if fp == 0:  # only promote if zero false positives
        if pattern["confidence"] == "candidate" and fires >= PROMOTE_AFTER_FIRES:
            pattern["confidence"] = "low"
            store.log_event(cwd, {
                "type": "pattern_promoted",
                "name": pattern_name,
                "to": "low",
            })
        elif pattern["confidence"] == "low" and fires >= PROMOTE_AFTER_FIRES * 3:
            pattern["confidence"] = "high"
            store.log_event(cwd, {
                "type": "pattern_promoted",
                "name": pattern_name,
                "to": "high",
            })

    save_pattern(cwd, pattern)


def report_false_positive(cwd: Path, pattern_name: str):
    """
    Called when a finding from this pattern gets resolved with note containing
    'false positive' or 'fp'. Demotes the pattern.
    """
    pattern = load_pattern(cwd, pattern_name)
    if not pattern:
        return

    pattern["false_positives"] = pattern.get("false_positives", 0) + 1

    if pattern["false_positives"] >= DEMOTE_AFTER_FALSE_POS:
        pattern["demotions"] = pattern.get("demotions", 0) + 1
        pattern["false_positives"] = 0  # reset

        # Demote
        idx = CONFIDENCE_LEVELS.index(pattern["confidence"])
        if idx > 0:
            pattern["confidence"] = CONFIDENCE_LEVELS[idx - 1]
            store.log_event(cwd, {
                "type": "pattern_demoted",
                "name": pattern_name,
                "to": pattern["confidence"],
            })

        # Kill if demoted too many times
        if pattern["demotions"] >= KILL_AFTER_DEMOTIONS:
            pattern["status"] = "killed"
            store.log_event(cwd, {
                "type": "pattern_killed",
                "name": pattern_name,
                "reason": "too many false positives",
            })

    save_pattern(cwd, pattern)


def prune_stale_patterns(cwd: Path):
    """Demote patterns that haven't fired in STALE_DAYS days."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=STALE_DAYS)
    patterns = load_all_patterns(cwd)

    for pattern in patterns:
        if pattern.get("status") != "active":
            continue
        if pattern["confidence"] == "candidate":
            # Candidates that never fired get killed faster (7 days)
            created_at = parse_iso(pattern.get("created_at"))
            if created_at and (now - created_at).days > 7:
                pattern["status"] = "killed"
                store.log_event(cwd, {
                    "type": "pattern_killed",
                    "name": pattern["name"],
                    "reason": "candidate never fired",
                })
                save_pattern(cwd, pattern)
            continue

        last_fired = parse_iso(pattern.get("last_fired"))
        if not last_fired or last_fired < cutoff:
            # Demote
            idx = CONFIDENCE_LEVELS.index(pattern["confidence"])
            if idx > 0:
                pattern["confidence"] = CONFIDENCE_LEVELS[idx - 1]
            else:
                pattern["status"] = "killed"
            store.log_event(cwd, {
                "type": "pattern_demoted",
                "name": pattern["name"],
                "reason": "stale",
            })
            save_pattern(cwd, pattern)


# ─── Persistence ─────────────────────────────────────────────────────────────

def patterns_dir(cwd: Path) -> Path:
    return store.vc_dir(cwd) / "patterns"


def load_all_patterns(cwd: Path) -> List[Dict]:
    pdir = patterns_dir(cwd)
    if not pdir.exists():
        return []
    out = []
    for f in sorted(pdir.glob("*.json")):
        p = store.read_json(f, default=None)
        if p:
            out.append(p)
    return out


def load_pattern(cwd: Path, name: str) -> Optional[Dict]:
    path = patterns_dir(cwd) / f"{name}.json"
    return store.read_json(path, default=None)


def save_pattern(cwd: Path, pattern: dict) -> bool:
    pdir = patterns_dir(cwd)
    pdir.mkdir(parents=True, exist_ok=True)
    name = pattern.get("name")
    if not name:
        return False
    return store.write_json(pdir / f"{name}.json", pattern)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def sanitize_name(name: str) -> str:
    """Convert pattern name to safe filename."""
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9_-]', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:64] or "unnamed"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
