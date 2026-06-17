#!/usr/bin/env python3
"""
VibeCheck guardrails.

Validates that the analyzer subagent didn't:
  - Modify any source files
  - Write outside .vibecheck/
  - Read or include sensitive file contents in findings
  - Create excessive findings or patterns
  - Include obvious prompt injection attempts in findings text

Called by the stop hook AFTER the analyzer subprocess completes.
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple
import store

# ─── File access constraints ─────────────────────────────────────────────────

SENSITIVE_FILE_PATTERNS = [
    re.compile(r'(^|/)\.env(\..*)?$'),     # .env, .env.local, .env.production
    re.compile(r'(^|/)\.aws/credentials'),
    re.compile(r'(^|/)\.ssh/'),
    re.compile(r'\.pem$'),
    re.compile(r'\.key$'),
    re.compile(r'(^|/)id_rsa'),
    re.compile(r'secrets?\.(json|yaml|yml|txt)$'),
    re.compile(r'(^|/)\.git/'),  # don't read git internals
]


def is_sensitive_path(file_path: Path) -> bool:
    """Check if a file matches a sensitive pattern that analyzer should never read."""
    s = str(file_path).replace("\\", "/")
    for pattern in SENSITIVE_FILE_PATTERNS:
        if pattern.search(s):
            return True
    return False


def is_within_vibecheck(file_path: Path, cwd: Path) -> bool:
    """Check if file is inside the .vibecheck/ directory."""
    try:
        resolved = file_path.resolve()
        vg = (cwd / ".vibecheck").resolve()
        return str(resolved).startswith(str(vg))
    except Exception:
        return False


def is_within_project(file_path: Path, cwd: Path) -> bool:
    """Check if file is inside the project root (not anywhere else on disk)."""
    try:
        resolved = file_path.resolve()
        return str(resolved).startswith(str(cwd.resolve()))
    except Exception:
        return False


# ─── Pre-analysis: filter session_files.txt ──────────────────────────────────

def filter_session_files(cwd: Path, files: List[Path]) -> List[Path]:
    """
    Strip sensitive files from the list before the analyzer ever sees them.
    Logs anything filtered.
    """
    safe = []
    filtered = []
    for f in files:
        if is_sensitive_path(f):
            filtered.append(str(f))
            continue
        if not is_within_project(f, cwd):
            filtered.append(str(f))
            continue
        if is_within_vibecheck(f, cwd):
            filtered.append(str(f))
            continue
        safe.append(f)

    if filtered:
        store.log_event(cwd, {
            "type": "guardrail_blocked",
            "stage": "pre_analysis",
            "reason": "sensitive_files_filtered",
            "files": filtered,
        })

    return safe


# ─── Post-analysis: detect filesystem violations ─────────────────────────────

def snapshot_source_files(cwd: Path, files: List[Path]) -> Dict[str, str]:
    """
    Take a content hash snapshot of source files BEFORE analysis runs.
    Used to detect if analyzer modified anything.
    """
    import hashlib
    snapshot = {}
    for f in files:
        try:
            content = f.read_bytes()
            snapshot[str(f)] = hashlib.sha256(content).hexdigest()
        except Exception:
            continue
    return snapshot


def verify_no_source_modifications(cwd: Path, snapshot: Dict[str, str]) -> List[str]:
    """
    Compare current file hashes against snapshot.
    Returns list of files that were modified by analyzer (should be empty).
    """
    import hashlib
    modified = []
    for path_str, original_hash in snapshot.items():
        path = Path(path_str)
        if not path.exists():
            modified.append(f"{path_str} (deleted)")
            continue
        try:
            current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if current_hash != original_hash:
                modified.append(path_str)
        except Exception:
            continue

    if modified:
        store.log_event(cwd, {
            "type": "guardrail_violation",
            "stage": "post_analysis",
            "severity": "high",
            "reason": "source_files_modified_by_analyzer",
            "files": modified,
        })

    return modified


# ─── Finding validation ──────────────────────────────────────────────────────

INJECTION_PATTERNS = [
    re.compile(r'ignore (previous|all|prior) (instructions|rules)', re.IGNORECASE),
    re.compile(r'you are (now|actually)', re.IGNORECASE),
    re.compile(r'<\s*system\s*>', re.IGNORECASE),
    re.compile(r'<\|.*?\|>'),
    re.compile(r'\[INST\]'),
]

# Length limits — these are sanity caps to prevent storage abuse,
# NOT to constrain the analyzer's expressiveness.
# title and why must be brief because they show in summary lines.
# fix_prompt and details can be long because they're shown on demand.
MAX_TITLE_LEN = 200       # shown in summary lines, must stay short
MAX_WHY_LEN = 500         # shown in summary too
MAX_FIX_PROMPT_LEN = 5000 # shown only when user expands — generous
MAX_DETAILS_LEN = 20000   # shown only on detail view — very generous
MAX_NEW_FINDINGS_PER_RUN = 5


def validate_findings_diff(cwd: Path, before: List[Dict], after: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Validate that new findings added by the analyzer are well-formed.
    Returns (cleaned_findings, list_of_issues).

    Strips findings that:
      - Have prompt injection attempts in their text
      - Exceed max sizes
      - Reference files outside the project
      - Lack required schema fields
      - Contain content that looks like leaked file contents (env vars, keys)
    """
    before_ids = {f.get("id") for f in before}
    new_findings = [f for f in after if f.get("id") not in before_ids]

    issues = []

    # Cap on new findings per run
    if len(new_findings) > MAX_NEW_FINDINGS_PER_RUN:
        issues.append(f"analyzer created {len(new_findings)} findings, max is {MAX_NEW_FINDINGS_PER_RUN}")
        # Keep only first N
        kept_ids = {f["id"] for f in new_findings[:MAX_NEW_FINDINGS_PER_RUN]}
        before_ids_plus_kept = before_ids | kept_ids
        after = [f for f in after if f.get("id") in before_ids_plus_kept]
        new_findings = new_findings[:MAX_NEW_FINDINGS_PER_RUN]

    cleaned_after = list(before)  # start with what was there before

    for finding in new_findings:
        violations = validate_single_finding(cwd, finding)
        # Distinguish fatal vs non-fatal violations.
        # Fatal: drops finding entirely.
        # Non-fatal: kept with auto-repair (truncation, etc).
        FATAL_PATTERNS = (
            "missing fields",
            "invalid severity",
            "prompt injection",
            "leaked content",
            "outside project",
        )
        is_fatal = any(any(fp in v for fp in FATAL_PATTERNS) for v in violations)

        if is_fatal:
            issues.append(f"{finding.get('id', '?')}: DROPPED — {', '.join(violations)}")
            store.log_event(cwd, {
                "type": "guardrail_violation",
                "stage": "finding_validation",
                "finding_id": finding.get("id"),
                "violations": violations,
                "action": "dropped",
            })
            continue

        if violations:  # non-fatal — keep finding but log
            issues.append(f"{finding.get('id', '?')}: REPAIRED — {', '.join(violations)}")
            store.log_event(cwd, {
                "type": "guardrail_repair",
                "finding_id": finding.get("id"),
                "violations": violations,
            })

        cleaned_after.append(finding)

    return cleaned_after, issues


def validate_single_finding(cwd: Path, finding: Dict) -> List[str]:
    """Returns list of violations. Empty list = clean."""
    violations = []

    # Schema check
    required = {"id", "severity", "title", "why", "fix_prompt", "status"}
    missing = required - set(finding.keys())
    if missing:
        violations.append(f"missing fields: {missing}")
        return violations  # don't bother with rest

    # Severity valid
    if finding["severity"] not in {"CRITICAL", "PITFALL", "HYGIENE", "GOOD_TO_HAVE"}:
        violations.append(f"invalid severity: {finding['severity']}")

    # Length checks — TRUNCATE rather than reject, so user still gets the finding
    if len(finding.get("title", "")) > MAX_TITLE_LEN:
        finding["title"] = finding["title"][:MAX_TITLE_LEN - 3] + "..."
        violations.append("title truncated (was too long for summary line)")
    if len(finding.get("why", "")) > MAX_WHY_LEN:
        # Move overflow to details rather than dropping
        original_why = finding["why"]
        finding["why"] = original_why[:MAX_WHY_LEN - 3] + "..."
        finding["details"] = (finding.get("details", "") + "\n\n" + original_why).strip()
        violations.append("why truncated and moved to details")
    if len(finding.get("fix_prompt", "")) > MAX_FIX_PROMPT_LEN:
        finding["fix_prompt"] = finding["fix_prompt"][:MAX_FIX_PROMPT_LEN]
        violations.append("fix_prompt truncated")
    if len(finding.get("details", "")) > MAX_DETAILS_LEN:
        finding["details"] = finding["details"][:MAX_DETAILS_LEN]
        violations.append("details truncated")

    # Prompt injection in any text field
    text_fields = [
        finding.get("title", ""),
        finding.get("why", ""),
        finding.get("fix_prompt", ""),
    ]
    combined = " ".join(text_fields)
    for pattern in INJECTION_PATTERNS:
        if pattern.search(combined):
            violations.append("contains prompt injection markers")
            break

    # Leaked secret detection in finding text — analyzer shouldn't include
    # actual secrets in findings (just say "secret found", not the secret itself)
    leak_patterns = [
        re.compile(r'sk_live_[a-zA-Z0-9]{10,}'),
        re.compile(r'sk-[a-zA-Z0-9]{20,}'),
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'ghp_[a-zA-Z0-9]{30,}'),
    ]
    for pattern in leak_patterns:
        if pattern.search(combined):
            violations.append("contains apparent secret value (analyzer leaked content)")
            break

    # File path must be within project
    file_ref = finding.get("file", "")
    if file_ref:
        # Strip line numbers (file.js:42 → file.js)
        path_part = file_ref.split(":")[0]
        if path_part:
            try:
                p = Path(path_part)
                if p.is_absolute():
                    if not is_within_project(p, cwd):
                        violations.append(f"file path outside project: {path_part}")
            except Exception:
                pass

    return violations


# ─── Pattern proposal validation ─────────────────────────────────────────────

def validate_proposed_patterns(cwd: Path, before_patterns: List[Dict], after_patterns: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Validate new patterns proposed by analyzer.
    Limit: 1 new pattern per run.
    """
    before_names = {p.get("name") for p in before_patterns}
    new_patterns = [p for p in after_patterns if p.get("name") not in before_names]

    issues = []
    if len(new_patterns) > 1:
        issues.append(f"analyzer proposed {len(new_patterns)} patterns, max is 1")
        # Keep only first
        kept = new_patterns[:1]
        kept_names = {p["name"] for p in kept}
        after_patterns = [p for p in after_patterns if p.get("name") in (before_names | kept_names)]

    return after_patterns, issues


# ─── Master post-analysis check ──────────────────────────────────────────────

def run_post_analysis_guards(cwd: Path, source_snapshot: Dict[str, str], findings_before: List[Dict]) -> Dict:
    """
    Master guardrail check — call after analyzer subprocess completes.
    Validates everything, repairs what it can, logs violations.
    Returns dict with summary of what happened.
    """
    result = {
        "source_modifications": [],
        "finding_issues": [],
        "pattern_issues": [],
        "violations_logged": 0,
    }

    # 1. No source files were modified
    modified = verify_no_source_modifications(cwd, source_snapshot)
    if modified:
        result["source_modifications"] = modified
        result["violations_logged"] += 1

    # 2. Findings are well-formed and bounded
    findings_after = store.load_findings(cwd)
    cleaned_findings, finding_issues = validate_findings_diff(cwd, findings_before, findings_after)
    if finding_issues:
        result["finding_issues"] = finding_issues
        result["violations_logged"] += len(finding_issues)
        # Save cleaned version back
        store.save_findings(cwd, cleaned_findings)
        store.rebuild_summary(cwd, cleaned_findings)

    return result
