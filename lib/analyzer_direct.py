"""
Direct LLM analyzer — single claude -p call with all context pre-loaded.
Replaces the agent subprocess approach. Runs synchronously in ~15-30s.
"""
import json, os, subprocess, datetime
from pathlib import Path

SEVERITY_PROMPT = """You are a security and code quality analyzer. Analyze the code and return findings as JSON.

SEVERITY RULES — apply strictly:

CRITICAL: Could a bad actor exploit this, or could it cause data loss in production?
- Route handles user data without auth check → CRITICAL
- User input in DB query without parameterization → CRITICAL
- User-controlled path in file read/write → CRITICAL
- Payment/webhook endpoint without signature verification → CRITICAL
- File upload without type/size validation → CRITICAL
- API leaks data the requester shouldn't see → CRITICAL
- Secrets hardcoded in source → CRITICAL

PITFALL: Architectural trap, no immediate security risk:
- Custom auth/JWT instead of using library → PITFALL
- In-memory rate limiting (doesn't survive restarts/scale) → PITFALL
- New feature built on top of broken existing code → PITFALL
- Premature optimization with clear evidence → PITFALL

HYGIENE: Repository health:
- Tests missing for newly built non-trivial feature → HYGIENE
- Unhandled async errors (await without try/catch in critical paths) → HYGIENE
- README drift after major feature → HYGIENE

GOOD_TO_HAVE: Minor improvements to working, safe code only:
- Rate limiting on public endpoints → GOOD_TO_HAVE
- Input validation on user-facing forms → GOOD_TO_HAVE

DROP entirely (do not report):
- Large files that could be split
- Missing comments or JSDoc
- Console.log unless leaking secrets
- Unconventional but working approaches
- Anything already in existing_findings

RE-VERIFICATION: For each entry in existing_findings where status=open, check if the issue
is still present in the provided code. If fixed, include its id in auto_resolved.

OUTPUT FORMAT — respond with only valid JSON, no other text:
{
  "findings": [
    {
      "severity": "CRITICAL|PITFALL|HYGIENE|GOOD_TO_HAVE",
      "title": "Brief plain-English title under 120 chars",
      "file": "relative/path/to/file.ext:lineNumber",
      "why": "Concrete consequence if unfixed, under 300 chars",
      "details": "Optional longer context, examples, what good code looks like",
      "fix_prompt": "Paste-ready instruction for Claude to fix this. Be specific."
    }
  ],
  "auto_resolved": ["vg-001", "vg-002"]
}

Rules:
- Max 5 new findings
- Zero findings is valid — don't invent problems
- Never include secret values
- findings array can be empty: {"findings": [], "auto_resolved": []}
"""


def run(cwd: Path, selected_files: list, session_id: str, debug_log=None) -> bool:
    """
    Run analysis synchronously using claude -p with pre-loaded context.
    Returns True if analysis ran, False if skipped.
    """
    claude_bin = _find_claude_bin()
    if not claude_bin:
        if debug_log: debug_log("direct analyzer: no claude bin found")
        return False

    # Read file contents
    file_contents = {}
    for fp in selected_files:
        try:
            content = Path(fp).read_text(errors="replace")
            rel = Path(fp).relative_to(cwd) if Path(fp).is_absolute() else Path(fp)
            file_contents[str(rel)] = content
        except Exception as e:
            if debug_log: debug_log(f"direct analyzer: could not read {fp}: {e}")

    if not file_contents:
        if debug_log: debug_log("direct analyzer: no readable files")
        return False

    # Load existing findings for dedup + re-verification
    try:
        from store import load_findings
        existing = load_findings(cwd)
        open_findings = [f for f in existing if f.get("status", "open") == "open"]
    except Exception:
        existing, open_findings = [], []

    # Build prompt
    prompt = _build_prompt(file_contents, open_findings)
    if debug_log: debug_log(f"direct analyzer: prompt {len(prompt)} chars, {len(file_contents)} files")

    # Call claude -p synchronously
    try:
        env = os.environ.copy()
        env["PATH"] = f"{Path.home() / '.local/bin'}:/usr/local/bin:/opt/homebrew/bin:{env.get('PATH', '')}"
        result = subprocess.run(
            [claude_bin, "-p", prompt, "--model", "claude-haiku-4-5-20251001",
             "--dangerously-skip-permissions"],
            cwd=str(cwd), capture_output=True, text=True, timeout=40, env=env,
        )
        raw = result.stdout.strip()
        if debug_log: debug_log(f"direct analyzer: exit={result.returncode} output_len={len(raw)}")
    except subprocess.TimeoutExpired:
        if debug_log: debug_log("direct analyzer: timed out after 50s")
        return False
    except Exception as e:
        if debug_log: debug_log(f"direct analyzer: subprocess error: {e}")
        return False

    # Parse response
    try:
        data = _extract_json(raw)
    except Exception as e:
        if debug_log: debug_log(f"direct analyzer: json parse error: {e} | raw: {raw[:200]}")
        return False

    # Write findings
    _apply_results(cwd, data, existing, session_id, debug_log)
    return True


def _build_prompt(file_contents: dict, open_findings: list) -> str:
    parts = [SEVERITY_PROMPT, "\n\n---\n\n## Files to analyze\n"]
    for path, content in file_contents.items():
        lines = content.split("\n")
        numbered = "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines))
        parts.append(f"\n### {path}\n```\n{numbered}\n```")

    if open_findings:
        parts.append("\n\n## Existing open findings (check if still valid)\n")
        for f in open_findings[:10]:
            parts.append(f"- {f.get('id')} ({f.get('severity')}): {f.get('title')} @ {f.get('file','')}")

    parts.append("\n\nAnalyze the files above and respond with JSON only.")
    return "\n".join(parts)


def _extract_json(raw: str) -> dict:
    # Strip markdown code fences if present
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    return json.loads(raw.strip())


def _apply_results(cwd: Path, data: dict, existing: list, session_id: str, debug_log):
    from store import load_findings, vg_dir, log_event
    import datetime

    now = datetime.datetime.utcnow().isoformat() + "Z"
    findings = load_findings(cwd)
    next_id = _next_id(findings)

    new_findings = data.get("findings", [])
    auto_resolved = set(data.get("auto_resolved", []))

    added = 0
    for raw_f in new_findings[:5]:
        sev = raw_f.get("severity", "")
        if sev not in ("CRITICAL", "PITFALL", "HYGIENE", "GOOD_TO_HAVE"):
            continue
        title = raw_f.get("title", "")
        # Skip if same title already open
        if any(f.get("title") == title and f.get("status", "open") == "open" for f in findings):
            continue
        fid = f"vg-{next_id:03d}"
        next_id += 1
        entry = {
            "id": fid, "severity": sev, "title": title,
            "file": raw_f.get("file", ""),
            "why": raw_f.get("why", ""),
            "details": raw_f.get("details", ""),
            "fix_prompt": raw_f.get("fix_prompt", ""),
            "status": "open", "source": "live",
            "tags": [], "detected_at": now, "session_id": session_id,
        }
        findings.append(entry)
        log_event(cwd, {"type": "finding_added", "finding_id": fid,
                        "severity": sev, "title": title, "source": "live"})
        added += 1

    # Auto-resolve stale findings
    resolved = 0
    for f in findings:
        if f.get("id") in auto_resolved and f.get("status", "open") == "open":
            f["status"] = "resolved"
            f["resolved_at"] = now
            f["resolution_note"] = "auto-resolved: issue no longer detected"
            resolved += 1

    (vg_dir(cwd) / "findings.json").write_text(json.dumps(findings, indent=2))

    # Update summary
    _update_summary(cwd, findings)

    log_event(cwd, {
        "type": "analysis_run", "files_analyzed": 0,
        "findings_added": added, "auto_resolved": resolved,
        "patterns_proposed": 0, "skills_proposed": 0,
    })

    if debug_log:
        debug_log(f"direct analyzer: +{added} findings, {resolved} auto-resolved")


def _update_summary(cwd: Path, findings: list):
    from store import vg_dir
    open_f = [f for f in findings if f.get("status", "open") == "open"]
    counts = {}
    for f in open_f:
        s = f.get("severity", "OTHER")
        counts[s] = counts.get(s, 0) + 1
    summary = {"total_open": len(open_f), "counts": counts,
               "last_updated": datetime.datetime.utcnow().isoformat() + "Z"}
    (vg_dir(cwd) / "summary.json").write_text(json.dumps(summary, indent=2))


def _next_id(findings: list) -> int:
    ids = [int(f["id"].split("-")[1]) for f in findings if f.get("id", "").startswith("vg-")]
    return max(ids, default=0) + 1


def _find_claude_bin():
    candidates = [
        os.environ.get("CLAUDE_BIN"),
        str(Path.home() / ".local/bin/claude"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
    ]
    for p in candidates:
        if p and Path(p).is_file() and os.access(p, os.X_OK):
            return p
    try:
        r = subprocess.run(["which", "claude"], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None
