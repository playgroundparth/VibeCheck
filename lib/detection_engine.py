#!/usr/bin/env python3
"""
VibeCheck detection engine — sync, regex-based evidence generation.

Contract:
  - run(cwd, changed_files) → List[Evidence]
  - Completes in <100ms (no subprocess, no I/O beyond reading changed files + .env.example)
  - Returns Evidence objects: structured observations with confidence tier
  - Evidence is NOT findings — Claude confirms evidence and decides whether to write a finding

Boundary rule:
  This module uses regex and lightweight structural checks only:
    - Positive regex match (is this pattern present?)
    - Negative regex match (is the mitigation absent from this file?)
    - Line-order adjacency (does A appear before B in the same file?)
    - Cross-file presence (is VAR_NAME in .env.example?)

  It must NOT implement:
    - Control-flow analysis         → belongs in Semgrep (async, Enhanced tier)
    - Taint propagation             → belongs in Semgrep (async, Enhanced tier)
    - Inter-file data-flow          → belongs in Graphify (async, Pro tier)
    - AST traversal                 → belongs in Semgrep (async, Enhanced tier)

  If you find yourself building a "context window" to track variable state → stop.
  That rule goes in Semgrep.

Evidence confidence tiers:
  high   — regex confirmed BOTH the risk AND absence of mitigation in same file
           (or source is semgrep/gitleaks/graphify — AST/exact confirmed)
  medium — risk pattern confirmed by regex, mitigation uncertain
           (Claude reads and confirms before writing finding)
  low    — single-sided heuristic match only
           (Claude must clearly see the issue to write a finding)
"""

import re
import os
from pathlib import Path
from typing import List, Dict


# ── Skip lists (reused from static_checks.py) ─────────────────────────────────

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".pdf", ".zip", ".tar", ".gz",
    ".lock",
}

SOURCE_EXTENSIONS = {
    ".js", ".ts", ".jsx", ".tsx", ".py", ".go", ".rb", ".php",
    ".java", ".cs", ".yaml", ".yml", ".toml", ".json",
    ".sh", ".bash", ".zsh",
}

MAX_FILE_SIZE_BYTES = 500_000  # skip files >500KB — likely generated

# ── False positive guards ──────────────────────────────────────────────────────
# Lines matching any of these are skipped for secret/injection patterns.

FALSE_POSITIVE_GUARDS = [
    r"process\.env\.",
    r"os\.environ",
    r"os\.getenv",
    r"config\.",
    r"settings\.",
    r"\$\{",           # template literals
    r"YOUR_",          # placeholder
    r"<YOUR",
    r"example",
    r"placeholder",
    r"REPLACE",
    r"sanitize",
    r"escape",
    r"validate",
    r"encodeURIComponent",
    r"parameterize",
    r"prepared",
    r"\.escape\(",
]

# ── Secret patterns ────────────────────────────────────────────────────────────

SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID hardcoded in source"),
    (r"aws_secret_access_key\s*=\s*[\"'][^\"']{20,}[\"']", "AWS Secret Key hardcoded"),
    (r"sk_live_[0-9a-zA-Z]{24,}", "Stripe live secret key hardcoded"),
    (r"sk_test_[0-9a-zA-Z]{24,}", "Stripe test secret key hardcoded"),
    (r"(?i)(api_key|apikey|api_secret)\s*[=:]\s*[\"'][a-zA-Z0-9_\-]{20,}[\"']", "API key hardcoded"),
    (r"(?i)(jwt_secret|jwt_key|secret_key)\s*[=:]\s*[\"'][^\"']{8,}[\"']", "JWT secret hardcoded"),
    (r"(?i)(postgres|mysql|mongodb)://[^:]+:[^@]+@", "Database URL with credentials hardcoded"),
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key possibly hardcoded"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token hardcoded"),
    (r"github_pat_[a-zA-Z0-9_]{82}", "GitHub Fine-grained PAT hardcoded"),
    (r"(?i)password\s*=\s*[\"'][^\"']{6,}[\"']", "Password hardcoded in source"),
]

# ── Webhook verification: known verify patterns ───────────────────────────────
# If ANY of these appears in the file, signature verification is present.

WEBHOOK_VERIFY_PATTERNS = re.compile(
    r"constructEvent|webhooks\.verify|svix\.verify|wh\.verify|"
    r"timingSafeEqual|hmac\.compare_digest|validateWebhook|"
    r"x-hub-signature|verifySignature|stripe\.webhooks",
    re.IGNORECASE,
)

# File path patterns that suggest this is a webhook handler
WEBHOOK_PATH_PATTERN = re.compile(
    r"webhook|stripe[_-]?handler|payment[_-]?handler",
    re.IGNORECASE,
)

# ── SQL injection patterns ─────────────────────────────────────────────────────

SQL_INJECTION_PATTERN = re.compile(
    r'(?:["\']SELECT\b[^"\'\\n]{0,120}["\']\s*\+|'
    r'SELECT\b[^"\'\n]{0,80}"\s*\+\s*\w|'
    r'SELECT\b[^"\'\n]{0,80}\+\s*\w[^;]{0,30}(?:WHERE|FROM)|'
    r'(?:["\']INSERT\b[^"\'\\n]{0,80}["\']\s*\+|'
    r'"UPDATE\b[^"\'\n]{0,80}"\s*\+\s*\w))',
    re.IGNORECASE,
)

# ── Shell injection patterns ───────────────────────────────────────────────────

SHELL_INJECTION_PATTERN = re.compile(
    r"(?:execSync|exec|spawn)\s*\([^)]{0,60}\+\s*\w|"
    r"os\.system\s*\([^)]{0,60}\+|"
    r"subprocess\.(?:call|run|Popen)\s*\([^)]{0,80}\+",
    re.IGNORECASE,
)

# ── Unsafe deserialization patterns ───────────────────────────────────────────

UNSAFE_DESER_PATTERN = re.compile(
    r"pickle\.loads\s*\(|yaml\.load\s*\([^,)]*\)(?!\s*,\s*Loader)",
)

# ── Open redirect patterns ─────────────────────────────────────────────────────

OPEN_REDIRECT_PATTERN = re.compile(
    r"(?:res|response)\.redirect\s*\(\s*req\.(?:query|body|params)\.",
    re.IGNORECASE,
)

# ── Mutation testing config detection ─────────────────────────────────────────
# Presence of any of these means mutation testing is already configured.

MUTATION_CONFIG_GLOBS = [
    # JS/TS — Stryker
    ".stryker.conf.js", ".stryker.conf.mjs", ".stryker.conf.cjs",
    ".stryker.conf.json", "stryker.config.js", "stryker.config.mjs",
    # Python — mutmut
    "mutmut.toml", "setup.cfg",   # setup.cfg may have [mutmut] section
    # Rust — cargo-mutants
    # (no config file; presence of cargo-mutants in Cargo.toml checked separately)
]

# Test file name patterns — these are files we want to flag for mutation testing
TEST_FILE_PATTERNS = re.compile(
    r"\.test\.(ts|tsx|js|jsx)|\.spec\.(ts|tsx|js|jsx)|"
    r"(^|/)test_[^/]+\.py$|(^|/)conftest\.py$|[^/]+_test\.py$|"
    r"(^|/)__(tests|test)__/",
    re.IGNORECASE,
)

TEST_SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py"}


def _has_mutation_config(cwd: Path) -> bool:
    """Return True if any mutation testing config file exists in the project root."""
    for name in MUTATION_CONFIG_GLOBS:
        if (cwd / name).exists():
            return True
    # Check Cargo.toml for cargo-mutants
    cargo = cwd / "Cargo.toml"
    if cargo.exists():
        try:
            if "cargo-mutants" in cargo.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            pass
    # Check pom.xml/build.gradle for pitest
    for build_file in ["pom.xml", "build.gradle", "build.gradle.kts"]:
        bf = cwd / build_file
        if bf.exists():
            try:
                if "pitest" in bf.read_text(encoding="utf-8", errors="ignore"):
                    return True
            except Exception:
                pass
    # Check setup.cfg for [mutmut] section
    setup_cfg = cwd / "setup.cfg"
    if setup_cfg.exists():
        try:
            if "[mutmut]" in setup_cfg.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            pass
    return False


def _is_test_file(file_path: Path) -> bool:
    """Return True if this file looks like a test file."""
    if file_path.suffix not in TEST_SOURCE_EXTENSIONS:
        return False
    name = file_path.name.lower()
    path_str = str(file_path).replace("\\", "/")
    return bool(TEST_FILE_PATTERNS.search(path_str) or
                TEST_FILE_PATTERNS.search(name))


def _detect_test_no_mutation(file_path: Path, rel: str, cwd: Path) -> List[Dict]:
    """
    MEDIUM confidence: test file written but no mutation testing configured.

    AI writes both the implementation and the tests. AI-generated tests routinely
    pass while testing nothing — happy path only, assertions that confirm code ran
    rather than that it was correct. Mutation testing is the only reliable way to
    verify tests would catch a real bug.

    Only fires once per run (caller deduplicates by checking cwd already flagged).
    """
    if not _is_test_file(file_path):
        return []
    if _has_mutation_config(cwd):
        return []

    # Detect language to give the right setup command
    suffix = file_path.suffix.lower()
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        lang = "js"
        setup_cmd = "npx stryker init"
        run_cmd = "npx stryker run"
        tool = "Stryker"
    elif suffix == ".py":
        lang = "python"
        setup_cmd = "pip install mutmut && mutmut run"
        run_cmd = "mutmut run"
        tool = "mutmut"
    else:
        return []

    return [_make_evidence(
        pattern_id="TEST-01",
        confidence="high",
        confidence_reason=(
            f"test file written ({file_path.name}) but no {tool} config found in project"
        ),
        file_rel=rel,
        line=1,
        matched_text=file_path.name,
        suggested_severity="PITFALL",
        check_question=(
            f"Mutation testing is not configured. AI-generated tests routinely pass while "
            f"verifying nothing. Run `{setup_cmd}` to set up {tool}, then `{run_cmd}` to find "
            f"which of your tests would miss a real bug. Write the finding and include the setup "
            f"command in the fix_prompt."
        ),
    )]


# ── Env var patterns ───────────────────────────────────────────────────────────

ENV_VAR_PATTERNS = [
    re.compile(r"process\.env\.([A-Z_][A-Z0-9_]+)"),
    re.compile(r"os\.environ(?:\.get)?\(['\"]([A-Z_][A-Z0-9_]+)['\"]"),
    re.compile(r"ENV\[['\"]([A-Z_][A-Z0-9_]+)['\"]\]"),
    re.compile(r"getenv\(['\"]([A-Z_][A-Z0-9_]+)['\"]"),
]

ENV_SKIP_VARS = {
    "NODE_ENV", "PORT", "HOST", "PWD", "HOME", "USER", "PATH", "SHELL", "TZ",
    "CI", "GITHUB_ACTIONS", "VERCEL", "VERCEL_ENV", "VERCEL_URL",
    "RAILWAY_ENVIRONMENT", "FLY_APP_NAME", "RENDER", "HEROKU_APP_NAME",
}


# ── Evidence helpers ──────────────────────────────────────────────────────────

def _make_evidence(
    pattern_id: str,
    confidence: str,
    confidence_reason: str,
    file_rel: str,
    line: int,
    matched_text: str,
    suggested_severity: str,
    check_question: str,
) -> Dict:
    return {
        "pattern_id": pattern_id,
        "source": "regex",
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "file": file_rel,
        "line": line,
        "matched_text": matched_text.strip()[:200],  # cap length for injection safety
        "suggested_severity": suggested_severity,
        "check_question": check_question,
    }


def _fp_guard(line: str) -> bool:
    """Return True if this line matches a false-positive guard — skip it."""
    return any(re.search(guard, line, re.IGNORECASE) for guard in FALSE_POSITIVE_GUARDS)


def _is_comment(line: str) -> bool:
    s = line.strip()
    return s.startswith("#") or s.startswith("//") or s.startswith("*")


def _rel(file_path: Path, cwd: Path) -> str:
    try:
        return str(file_path.relative_to(cwd))
    except ValueError:
        return str(file_path)


# ── Per-file detectors ────────────────────────────────────────────────────────

def _detect_secrets(file_path: Path, content: str, rel: str) -> List[Dict]:
    """HIGH confidence: secret pattern matched + no false-positive guard on same line."""
    if file_path.suffix not in SOURCE_EXTENSIONS:
        return []
    lines = content.splitlines()
    for pattern_str, description in SECRET_PATTERNS:
        compiled = re.compile(pattern_str)
        for i, line in enumerate(lines, 1):
            if _is_comment(line):
                continue
            if compiled.search(line) and not _fp_guard(line):
                return [_make_evidence(
                    pattern_id="HARDCODED_SECRET",
                    confidence="high",
                    confidence_reason="secret pattern matched with no env-var or placeholder guard",
                    file_rel=rel,
                    line=i,
                    matched_text=line,
                    suggested_severity="CRITICAL",
                    check_question=(
                        f"Is this value a real secret hardcoded in source? "
                        f"If yes, move to environment variable immediately."
                    ),
                )]
    return []


def _detect_sql_injection(file_path: Path, content: str, rel: str) -> List[Dict]:
    """HIGH confidence: SQL string concat with no prepared-statement guard."""
    if file_path.suffix not in {".js", ".ts", ".jsx", ".tsx", ".py", ".go", ".rb", ".php"}:
        return []
    name = file_path.name.lower()
    if any(x in name for x in (".test.", ".spec.", "_test.", "test_")):
        return []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if _is_comment(line):
            continue
        if SQL_INJECTION_PATTERN.search(line) and not _fp_guard(line):
            return [_make_evidence(
                pattern_id="SQL_INJECTION",
                confidence="high",
                confidence_reason="SQL query built with string concatenation, no parameterize/prepared guard",
                file_rel=rel,
                line=i,
                matched_text=line,
                suggested_severity="CRITICAL",
                check_question=(
                    "Is user-controlled data concatenated into this SQL string? "
                    "Use parameterized queries instead."
                ),
            )]
    return []


def _detect_shell_injection(file_path: Path, content: str, rel: str) -> List[Dict]:
    """HIGH confidence: exec/execSync with string concatenation."""
    if file_path.suffix not in {".js", ".ts", ".jsx", ".tsx", ".py"}:
        return []
    name = file_path.name.lower()
    if any(x in name for x in (".test.", ".spec.", "_test.", "test_")):
        return []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if _is_comment(line):
            continue
        if SHELL_INJECTION_PATTERN.search(line) and not _fp_guard(line):
            return [_make_evidence(
                pattern_id="SHELL_INJECTION",
                confidence="high",
                confidence_reason="exec/execSync called with string concatenation, no sanitize guard",
                file_rel=rel,
                line=i,
                matched_text=line,
                suggested_severity="CRITICAL",
                check_question=(
                    "Is user-controlled input concatenated into this shell command? "
                    "Use argument arrays instead of string concatenation."
                ),
            )]
    return []


def _detect_unsafe_deser(file_path: Path, content: str, rel: str) -> List[Dict]:
    """HIGH confidence: pickle.loads or yaml.load without SafeLoader."""
    if file_path.suffix not in {".py"}:
        return []
    name = file_path.name.lower()
    if any(x in name for x in (".test.", ".spec.", "_test.", "test_")):
        return []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if _is_comment(line):
            continue
        if UNSAFE_DESER_PATTERN.search(line):
            return [_make_evidence(
                pattern_id="UNSAFE_DESER",
                confidence="high",
                confidence_reason="pickle.loads or yaml.load without SafeLoader — direct match",
                file_rel=rel,
                line=i,
                matched_text=line,
                suggested_severity="CRITICAL",
                check_question=(
                    "Is untrusted data deserialized here? "
                    "Replace pickle.loads with json, or use yaml.safe_load()."
                ),
            )]
    return []


def _detect_open_redirect(file_path: Path, content: str, rel: str) -> List[Dict]:
    """HIGH confidence: redirect target taken directly from user input."""
    if file_path.suffix not in {".js", ".ts", ".jsx", ".tsx"}:
        return []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if _is_comment(line):
            continue
        if OPEN_REDIRECT_PATTERN.search(line) and not _fp_guard(line):
            return [_make_evidence(
                pattern_id="OPEN_REDIRECT",
                confidence="high",
                confidence_reason="redirect target taken directly from req.query/body — no validation guard",
                file_rel=rel,
                line=i,
                matched_text=line,
                suggested_severity="PITFALL",
                check_question=(
                    "Is the redirect URL validated against an allowlist before use? "
                    "An unvalidated redirect enables phishing attacks."
                ),
            )]
    return []


def _detect_webhook_no_sig(file_path: Path, content: str, rel: str) -> List[Dict]:
    """
    MEDIUM confidence: file path suggests webhook handler, no verification pattern in file.

    Boundary: file-scope presence/absence check only. NOT control-flow analysis.
    If verify pattern is anywhere in the file, we skip (even if technically unreachable).
    """
    if not WEBHOOK_PATH_PATTERN.search(str(file_path)):
        return []
    if file_path.suffix not in {".js", ".ts", ".jsx", ".tsx", ".py"}:
        return []
    name = file_path.name.lower()
    if any(x in name for x in (".test.", ".spec.", "_test.", "test_")):
        return []

    # If any verification pattern appears in the file, skip
    if WEBHOOK_VERIFY_PATTERNS.search(content):
        return []

    # Look for the handler registration line to use as the evidence location
    handler_pattern = re.compile(
        r"(?:app|router|router)\.(?:post|get|put)\s*\(|"
        r"(?:export|module\.exports)\s*(?:default\s*)?(?:async\s*)?function|"
        r"async\s+function\s+\w+|"
        r"handler\s*=\s*async",
        re.IGNORECASE,
    )
    lines = content.splitlines()
    line_num = 1
    for i, line in enumerate(lines, 1):
        if handler_pattern.search(line):
            line_num = i
            matched = line
            break
    else:
        matched = lines[0] if lines else ""

    return [_make_evidence(
        pattern_id="WEBHOOK_NO_SIG",
        confidence="medium",
        confidence_reason="webhook endpoint file with no signature verification pattern found",
        file_rel=rel,
        line=line_num,
        matched_text=matched,
        suggested_severity="CRITICAL",
        check_question=(
            "Is stripe.webhooks.constructEvent() (or equivalent) called with the raw body "
            "before any body parsing? If not, anyone can send fake webhook events."
        ),
    )]


def _detect_env_undocumented(cwd: Path, changed_files: List[Path]) -> List[Dict]:
    """
    HIGH confidence: process.env.VAR used in code but VAR absent from .env.example.
    Cross-file presence check — safe (no control-flow reasoning).
    """
    env_example_path = None
    for name in [".env.example", ".env.example.local", "env.example", ".env.template", ".env.sample"]:
        candidate = cwd / name
        if candidate.exists():
            env_example_path = candidate
            break

    if env_example_path is None:
        return []  # No .env.example — _check_env_vars_documented in static_checks handles this

    example_content = env_example_path.read_text(encoding="utf-8", errors="ignore")
    example_vars = set(re.findall(r"^([A-Z_][A-Z0-9_]*)(?:\s*=.*)?$", example_content, re.MULTILINE))

    evidence = []
    seen_vars: set = set()
    source_exts = {".js", ".ts", ".jsx", ".tsx", ".py", ".rb", ".php", ".go"}

    for file_path in changed_files:
        if not file_path.exists() or file_path.suffix not in source_exts:
            continue
        if file_path.name.startswith(".env"):
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = _rel(file_path, cwd)
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            for pat in ENV_VAR_PATTERNS:
                for var in pat.findall(line):
                    if var in ENV_SKIP_VARS or var in seen_vars or var in example_vars:
                        continue
                    seen_vars.add(var)
                    evidence.append(_make_evidence(
                        pattern_id="ENV_VAR_UNDOCUMENTED",
                        confidence="high",
                        confidence_reason=f"{var} referenced in code but absent from {env_example_path.name}",
                        file_rel=rel,
                        line=i,
                        matched_text=line,
                        suggested_severity="CRITICAL",
                        check_question=(
                            f"Is {var} documented in {env_example_path.name}? "
                            f"If not, this will be undefined in every environment that's not yours."
                        ),
                    ))

    return evidence


# ── Main entry point ──────────────────────────────────────────────────────────

def run(cwd: Path, changed_files: List[Path]) -> List[Dict]:
    """
    Run all sync detectors against changed files.
    Returns at most 5 evidence items (high confidence first).
    Completes in <100ms on typical edit sizes.
    """
    all_evidence: List[Dict] = []

    for file_path in changed_files:
        if not file_path.exists():
            continue
        if file_path.suffix.lower() in SKIP_EXTENSIONS:
            continue
        try:
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
        except Exception:
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = _rel(file_path, cwd)

        all_evidence.extend(_detect_secrets(file_path, content, rel))
        all_evidence.extend(_detect_sql_injection(file_path, content, rel))
        all_evidence.extend(_detect_shell_injection(file_path, content, rel))
        all_evidence.extend(_detect_unsafe_deser(file_path, content, rel))
        all_evidence.extend(_detect_open_redirect(file_path, content, rel))
        all_evidence.extend(_detect_webhook_no_sig(file_path, content, rel))

    # Cross-file check: env vars undocumented
    all_evidence.extend(_detect_env_undocumented(cwd, changed_files))

    # Cross-file check: test file written but no mutation testing configured
    # (deduplicated — fire at most once per run regardless of how many test files changed)
    _mutation_flagged = False
    for file_path in changed_files:
        if _mutation_flagged:
            break
        if not file_path.exists():
            continue
        try:
            rel = _rel(file_path, cwd)
            ev = _detect_test_no_mutation(file_path, rel, cwd)
            if ev:
                all_evidence.extend(ev)
                _mutation_flagged = True
        except Exception:
            pass

    # Sort: high confidence first, then medium, then low
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    all_evidence.sort(key=lambda e: confidence_order.get(e.get("confidence", "low"), 2))

    # Return at most 5 (the most important ones)
    return all_evidence[:5]


def format_for_injection(evidence: List[Dict], next_finding_id: int, tier: str = "basic") -> str:
    """
    Format evidence list as a human-readable block for systemMessage injection.
    Claude reads this and confirms/denies each item.
    """
    if not evidence:
        return (
            f"[VibeCheck Detection] No issues detected (capability tier: {tier}). "
            f"Quick sanity check: confirm no hardcoded secrets, no unverified webhook bodies. "
            f"Next finding ID: vc-{next_finding_id:03d}."
        )

    lines = [f"[VibeCheck Detection] Found {len(evidence)} evidence item(s) (tier: {tier}):"]
    lines.append("")

    current_id = next_finding_id
    for idx, ev in enumerate(evidence, 1):
        conf = ev.get("confidence", "medium")
        pattern = ev.get("pattern_id", "UNKNOWN")
        file_loc = ev.get("file", "")
        line_num = ev.get("line", 0)
        matched = ev.get("matched_text", "")
        reason = ev.get("confidence_reason", "")
        question = ev.get("check_question", "")
        severity = ev.get("suggested_severity", "PITFALL")

        file_ref = f"{file_loc}:{line_num}" if line_num else file_loc

        lines.append(f"EVIDENCE-{idx:03d} [{pattern}] confidence:{conf}")
        lines.append(f"  File: {file_ref}")
        if matched:
            lines.append(f"  Found: `{matched[:120]}`")
        if reason:
            lines.append(f"  Reason: {reason}")
        lines.append(f"  Check: {question}")

        if conf == "high":
            lines.append(
                f"  → {severity} (vc-{current_id:03d}) — write finding unless clear mitigation in code"
            )
        elif conf == "medium":
            lines.append(
                f"  → {severity} (vc-{current_id:03d}) if confirmed by reading the cited file"
            )
        else:
            lines.append(
                f"  → {severity} (vc-{current_id:03d}) only if code clearly demonstrates the problem"
            )
        lines.append("")
        current_id += 1

    lines.append(
        f"Read cited file lines and confirm each item. "
        f"Write findings for confirmed items. Render VibeCheck footer."
    )
    return "\n".join(lines)
