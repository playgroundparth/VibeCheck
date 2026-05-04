#!/usr/bin/env python3
"""
VibeCheck data layer.
All reads/writes go through here. JSON-only, no markdown parsing.

Schema overview:
  findings.json   — array of finding objects
  timeline.json   — append-only event log (decisions, changes, milestones)
  memory.json     — structured project understanding
  summary.json    — cached counts for fast hook reads
  config.json     — user preferences
  patterns/       — learned check patterns, one JSON file each
"""

import json
import os
import time
import fcntl
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


# ─── Constants ───────────────────────────────────────────────────────────────

SEVERITIES = {"CRITICAL", "PITFALL", "HYGIENE", "GOOD_TO_HAVE"}
STATUSES = {"open", "resolved", "snoozed"}


# ─── Path helpers ─────────────────────────────────────────────────────────────

def vg_dir(cwd: Path) -> Path:
    return cwd / ".vibecheck"

def findings_path(cwd: Path) -> Path:
    return vg_dir(cwd) / "findings.json"

def timeline_path(cwd: Path) -> Path:
    return vg_dir(cwd) / "timeline.json"

def memory_path(cwd: Path) -> Path:
    return vg_dir(cwd) / "memory.json"

def summary_path(cwd: Path) -> Path:
    return vg_dir(cwd) / "summary.json"

def config_path(cwd: Path) -> Path:
    return vg_dir(cwd) / "config.json"

def patterns_dir(cwd: Path) -> Path:
    return vg_dir(cwd) / "patterns"

def lock_path(cwd: Path) -> Path:
    return vg_dir(cwd) / "analysis.lock"


# ─── Safe JSON read/write with file locking ───────────────────────────────────

def read_json(path: Path, default=None):
    """Read JSON file. Returns default if missing or corrupt."""
    if default is None:
        default = []
    try:
        if not path.exists():
            return default
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, data) -> bool:
    """Atomic write with file lock. Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f, indent=2, default=str)
            fcntl.flock(f, fcntl.LOCK_UN)
        tmp.replace(path)  # Atomic rename
        return True
    except Exception:
        return False


def append_json_array(path: Path, item: dict) -> bool:
    """Append an item to a JSON array file. Thread-safe."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            content = f.read().strip()
            if not content:
                data = []
            else:
                try:
                    data = json.loads(content)
                except Exception:
                    data = []
            data.append(item)
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, default=str)
            fcntl.flock(f, fcntl.LOCK_UN)
        return True
    except Exception:
        return False


# ─── Findings ─────────────────────────────────────────────────────────────────

def load_findings(cwd: Path) -> list:
    findings = read_json(findings_path(cwd), default=[])
    for f in findings:
        if f.get("status") is None:
            f["status"] = "open"
    return findings


def save_findings(cwd: Path, findings: list) -> bool:
    return write_json(findings_path(cwd), findings)


def add_finding(cwd: Path, finding: dict) -> Optional[str]:
    """
    Add a new finding. Auto-assigns ID. Returns ID or None on failure.
    finding must have: severity, title, file, why, fix_prompt
    Optional: source ("scan"|"live"), tags (list), details (long-form explanation)
    """
    if finding.get("severity") not in SEVERITIES:
        return None

    findings = load_findings(cwd)

    # Generate next ID
    existing_ids = [f.get("id", "vg-000") for f in findings]
    max_num = max(
        (int(i.split("-")[1]) for i in existing_ids if i.startswith("vg-")),
        default=0
    )
    new_id = f"vg-{max_num + 1:03d}"

    new_finding = {
        "id": new_id,
        "severity": finding["severity"],
        "title": finding["title"],
        "file": finding.get("file", ""),
        "why": finding["why"],
        "fix_prompt": finding["fix_prompt"],
        "details": finding.get("details", ""),  # NEW: optional long-form
        "status": "open",
        "source": finding.get("source", "live"),
        "tags": finding.get("tags", []),
        "detected_at": now_iso(),
        "session_id": finding.get("session_id", ""),
    }

    findings.append(new_finding)
    if not save_findings(cwd, findings):
        return None

    # Update summary cache
    rebuild_summary(cwd, findings)

    # Track metric (single source of truth for findings_created)
    try:
        import metrics
        metrics.record_finding_added(cwd)
    except Exception:
        pass

    # Log to timeline
    log_event(cwd, {
        "type": "finding_added",
        "finding_id": new_id,
        "severity": new_finding["severity"],
        "title": new_finding["title"],
        "source": new_finding["source"],
    })

    return new_id


def resolve_finding(cwd: Path, finding_id: str, note: str = "") -> bool:
    """Mark a finding as resolved."""
    findings = load_findings(cwd)
    is_false_positive = "false positive" in note.lower() or "fp" in note.lower()

    for f in findings:
        if f["id"] == finding_id:
            f["status"] = "resolved"
            f["resolved_at"] = now_iso()
            f["resolved_note"] = note
            break
    else:
        return False

    ok = save_findings(cwd, findings)
    if ok:
        rebuild_summary(cwd, findings)
        # Track metric
        try:
            import metrics
            metrics.record_finding_resolved(cwd, was_false_positive=is_false_positive)
        except Exception:
            pass
        log_event(cwd, {
            "type": "finding_resolved",
            "finding_id": finding_id,
            "note": note,
            "false_positive": is_false_positive,
        })
    return ok


def get_open_findings(cwd: Path) -> list:
    return [f for f in load_findings(cwd) if f.get("status") == "open"]


def is_already_known(cwd: Path, title: str, file: str) -> bool:
    """Prevent duplicate findings for same issue in same file."""
    findings = load_findings(cwd)
    for f in findings:
        if f.get("status") == "open" and f.get("file") == file:
            # Simple title similarity check — avoid obvious dupes
            if title.lower()[:40] == f.get("title", "").lower()[:40]:
                return True
    return False


def rebuild_summary(cwd: Path, findings: list = None):
    """Rebuild summary.json from findings. Call after any findings change."""
    if findings is None:
        findings = load_findings(cwd)
    open_findings = [f for f in findings if f.get("status") == "open"]
    counts = {s: 0 for s in SEVERITIES}
    for f in open_findings:
        sev = f.get("severity", "")
        if sev in counts:
            counts[sev] += 1
    summary = {
        "counts": counts,
        "total_open": len(open_findings),
        "total_all": len(findings),
        "updated_at": now_iso(),
    }
    write_json(summary_path(cwd), summary)
    return summary


def load_summary(cwd: Path) -> dict:
    return read_json(summary_path(cwd), default={
        "counts": {s: 0 for s in SEVERITIES},
        "total_open": 0,
        "total_all": 0,
    })


# ─── Timeline (append-only event log) ────────────────────────────────────────

def log_event(cwd: Path, event: dict):
    """
    Append an event to the timeline. Never modifies existing events.
    event should have: type, and any relevant fields.

    Event types used:
      session_start       — Claude Code session began
      task_completed      — user finished a task (files written)
      finding_added       — VibeCheck found something
      finding_resolved    — user resolved a finding
      decision_made       — important architectural/approach decision detected
      scan_run            — full codebase scan executed
      model_changed       — user switched analysis model
      pitfall_detected    — user might be reinventing or over-indexing
      test_reminder       — VibeCheck reminded user to test
      hygiene_flag        — repo hygiene issue detected
    """
    entry = {
        "ts": now_iso(),
        "type": event.get("type", "unknown"),
        **{k: v for k, v in event.items() if k != "type"},
    }
    append_json_array(timeline_path(cwd), entry)


def load_timeline(cwd: Path) -> list:
    return read_json(timeline_path(cwd), default=[])


def get_recent_timeline(cwd: Path, n: int = 20) -> list:
    """Get the N most recent timeline events."""
    return load_timeline(cwd)[-n:]


# ─── Memory (structured project understanding) ────────────────────────────────

def load_memory(cwd: Path) -> dict:
    return read_json(memory_path(cwd), default={
        "project": {},
        "stack": [],
        "features": [],
        "decisions": [],
        "known_risks": [],
        "last_updated": None,
    })


def update_memory(cwd: Path, updates: dict):
    """
    Merge updates into memory. Appends to list fields, replaces scalar fields.
    updates example:
      {
        "project": {"name": "MyApp", "type": "SaaS", "description": "..."},
        "stack": ["Next.js", "Supabase", "Stripe"],
        "features": ["auth", "payments", "dashboard"],
        "decisions": [{"what": "chose Supabase over Firebase", "why": "...", "when": "..."}]
      }
    """
    memory = load_memory(cwd)

    # Merge project info (dict — replace fields)
    if "project" in updates:
        memory["project"].update(updates["project"])

    # Stack/features — add new items, no duplicates
    for list_field in ("stack", "features", "known_risks"):
        if list_field in updates:
            existing = set(memory.get(list_field, []))
            for item in updates[list_field]:
                if item not in existing:
                    memory[list_field].append(item)
                    existing.add(item)

    # Decisions — append with timestamp
    if "decisions" in updates:
        for d in updates["decisions"]:
            if "when" not in d:
                d["when"] = now_iso()
            memory["decisions"].append(d)

    memory["last_updated"] = now_iso()
    write_json(memory_path(cwd), memory)

    # Log significant decisions to timeline
    if "decisions" in updates:
        for d in updates["decisions"]:
            log_event(cwd, {
                "type": "decision_made",
                "what": d.get("what", ""),
                "why": d.get("why", ""),
            })


# ─── Patterns ─────────────────────────────────────────────────────────────────

def load_patterns(cwd: Path) -> list:
    """Load all learned check patterns."""
    pdir = patterns_dir(cwd)
    if not pdir.exists():
        return []
    patterns = []
    for f in sorted(pdir.glob("*.json")):
        p = read_json(f, default=None)
        if p:
            patterns.append(p)
    return patterns


def save_pattern(cwd: Path, pattern: dict) -> bool:
    """
    Save a learned pattern.
    pattern must have: name, triggers_when, checks (list of strings)
    """
    pdir = patterns_dir(cwd)
    pdir.mkdir(parents=True, exist_ok=True)
    name = pattern.get("name", "").replace(" ", "-").lower()
    if not name:
        return False
    pattern["created_at"] = pattern.get("created_at", now_iso())
    pattern["times_fired"] = pattern.get("times_fired", 0)
    return write_json(pdir / f"{name}.json", pattern)


def increment_pattern_fired(cwd: Path, pattern_name: str):
    """Track how often a pattern fires — prune useless ones later."""
    pdir = patterns_dir(cwd)
    path = pdir / f"{pattern_name}.json"
    p = read_json(path, default=None)
    if p:
        p["times_fired"] = p.get("times_fired", 0) + 1
        p["last_fired"] = now_iso()
        write_json(path, p)


# ─── Config ───────────────────────────────────────────────────────────────────

MODELS = {
    "haiku": {
        "id": "claude-haiku-4-5-20251001",
        "label": "Claude Haiku",
        "cost_per_1m_input": 0.80,
        "cost_per_1m_output": 4.00,
        "avg_tokens_per_analysis": 2500,
        "avg_cost_per_analysis": 0.002,
    },
    "sonnet": {
        "id": "claude-sonnet-4-6",
        "label": "Claude Sonnet",
        "cost_per_1m_input": 3.00,
        "cost_per_1m_output": 15.00,
        "avg_tokens_per_analysis": 2500,
        "avg_cost_per_analysis": 0.018,
    },
}

DEFAULT_CONFIG = {
    "model": "haiku",
    "telemetry": False,  # Opt-in only, never enabled by default
    "version": "0.1.0",
    "installed_at": None,
}


def load_config(cwd: Path) -> dict:
    cfg = read_json(config_path(cwd), default={})
    return {**DEFAULT_CONFIG, **cfg}


def save_config(cwd: Path, updates: dict):
    cfg = load_config(cwd)
    cfg.update(updates)
    write_json(config_path(cwd), cfg)
    if "model" in updates:
        log_event(cwd, {"type": "model_changed", "model": updates["model"]})


def get_model_info(cwd: Path) -> dict:
    cfg = load_config(cwd)
    return MODELS.get(cfg.get("model", "haiku"), MODELS["haiku"])


# ─── Lock ────────────────────────────────────────────────────────────────────

def acquire_lock(cwd: Path, session_id: str = "") -> bool:
    """Write lock file. Returns True if acquired (not already locked)."""
    lp = lock_path(cwd)
    if lp.exists():
        # Check if stale (older than 2 minutes)
        try:
            age = time.time() - lp.stat().st_mtime
            if age < 120:
                return False  # Legitimate lock
        except Exception:
            pass
    try:
        lp.write_text(json.dumps({
            "session_id": session_id,
            "acquired_at": now_iso(),
        }))
        return True
    except Exception:
        return False


def release_lock(cwd: Path):
    lock_path(cwd).unlink(missing_ok=True)


def is_locked(cwd: Path) -> bool:
    lp = lock_path(cwd)
    if not lp.exists():
        return False
    # Stale after 2 minutes
    try:
        age = time.time() - lp.stat().st_mtime
        if age > 120:
            lp.unlink(missing_ok=True)
            return False
    except Exception:
        pass
    return True


# ─── Utilities ────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_initialized(cwd: Path) -> bool:
    return (vg_dir(cwd) / "config.json").exists()
