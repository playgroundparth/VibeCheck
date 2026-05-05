#!/usr/bin/env python3
"""
VibeCheck PostToolUse Hook.

Fires after Read/Write/Edit/MultiEdit tool calls.
- Extracts security-relevant project facts into .vibecheck/project_context.json.
- Auto-installs integration skill files when relevant code is detected.
- Detects active frameworks and writes .vibecheck/active_frameworks.json so Claude
  loads the right framework question prompts during its inline VibeCheck step.
Zero LLM calls — pure regex. Must complete in < 100ms.
"""
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import project, store, context_extractor

DEBUG = os.environ.get("VIBEGUARD_DEBUG") == "1"

WATCHED_TOOLS = {"Read", "Write", "Edit", "MultiEdit"}
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                   ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webp",
                   ".lock", ".sum"}

# Integration detection: pattern → (skill template filename, installed skill filename)
# Each pattern is matched against file content. Case-insensitive where appropriate.
INTEGRATION_SKILLS = {
    "stripe":   (re.compile(r"stripe|STRIPE_|payment_intent|constructEvent", re.I),
                 "stripe.md", "check-stripe-integration.md"),
    "supabase": (re.compile(r"supabase|SUPABASE_", re.I),
                 "supabase.md", "check-supabase-integration.md"),
    "clerk":    (re.compile(r"@clerk/|useAuth|currentUser|clerkClient", re.I),
                 "clerk.md", "check-clerk-integration.md"),
    "prisma":   (re.compile(r"PrismaClient|@prisma/client|prisma\.\w+\(|schema\.prisma"),
                 "prisma.md", "check-prisma-integration.md"),
    "openai":   (re.compile(r"openai|OPENAI_API_KEY|anthropic|ANTHROPIC_API_KEY", re.I),
                 "openai.md", "check-openai-integration.md"),
    "vercel":   (re.compile(r"@vercel/|maxDuration.*=.*\d|VERCEL_URL"),
                 "vercel.md", "check-vercel-integration.md"),
}

# ── Framework detection ──────────────────────────────────────────────────────
# Each entry: (content_pattern, path_pattern)
# Fires on Write/Edit/MultiEdit if EITHER pattern matches (content OR file path).
# Only the frameworks proven to add signal are auto-detected; the rest ship as files
# but Claude can load them manually via /vibecheck-review context.
FRAMEWORK_DETECTORS = {
    "event-driven": (
        re.compile(
            r"webhook|event\.type|constructEvent|\.subscribe\(|"
            r"messageHandler|queue\.process|\.on\(['\"][a-z]|"
            r"pub\.?sub|consumer|listener",
            re.I,
        ),
        re.compile(r"webhook|consumer|subscriber|listener|event[_-]handler", re.I),
    ),
    "irreversible-action": (
        re.compile(
            r"\.delete\(|\.destroy\(|\.remove\(|deleteUser|deleteAccount|"
            r"DELETE\s+FROM|DROP\s+TABLE|TRUNCATE\s+TABLE|"
            r"sendEmail|send_email|sendSMS|sendPush|notif.*send|"
            r"cancelSubscription|cancel_subscription|revokeAccess|"
            r"stripe\.charges\.create|createCharge",
            re.I,
        ),
        re.compile(r"delete|destroy|remove|cancel|revoke|purge", re.I),
    ),
    "billing-pricing": (
        re.compile(
            r"stripe\.|payment_intent|checkout\.session\.|invoice\.|"
            r"subscription\.(create|update|cancel)|createCustomer",
            re.I,
        ),
        re.compile(r"billing|payment|checkout|pricing|subscription", re.I),
    ),
    "async-scheduled": (
        re.compile(
            r"cron\.|\.schedule\(|inngest\.|new\s+Worker|"
            r"queue\.add\(|BullMQ|\.process\(|backgroundJob",
            re.I,
        ),
        re.compile(r"cron|scheduler|worker|job[_-]queue|background[_-]job", re.I),
    ),
    "concurrent-state": (
        re.compile(
            r"votes?\s*[\+\-]=\s*1|\bincrement\b.*votes?|"
            r"counter\s*[\+\-]=|\bvotes\s*\+\s*1\b|"
            r"\.increment\(\{|UPDATE.*SET.*=.*\+",
            re.I,
        ),
        re.compile(r"counter|vote[_-]?count|tally|increment", re.I),
    ),
}

ACTIVE_FRAMEWORKS_FILE = "active_frameworks.json"


def _detect_frameworks(content: str, file_path: str) -> set:
    """Return set of framework names that match this file."""
    matched = set()
    path_str = str(file_path).lower()
    for name, (content_pat, path_pat) in FRAMEWORK_DETECTORS.items():
        if content_pat.search(content) or path_pat.search(path_str):
            matched.add(name)
    return matched


def _update_active_frameworks(cwd: Path, new_frameworks: set, rel_path: str) -> None:
    """Union new_frameworks into .vibecheck/active_frameworks.json."""
    if not new_frameworks:
        return
    vg_dir = store.vg_dir(cwd)
    af_path = vg_dir / ACTIVE_FRAMEWORKS_FILE
    existing = set()
    existing_files = []
    if af_path.exists():
        try:
            data = json.loads(af_path.read_text())
            existing = set(data.get("frameworks", []))
            existing_files = data.get("files", [])
        except Exception:
            pass
    merged = sorted(existing | new_frameworks)
    files = list(dict.fromkeys(existing_files + [rel_path]))  # deduplicated, ordered
    af_path.write_text(json.dumps({
        "frameworks": merged,
        "files": files,
        "ts": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }, indent=2))


# Module-level cache of installed skill names. None = not yet loaded.
_installed_skills_cache = None  # type: set or None


def _skills_dir(claude_dir: Path) -> Path:
    return claude_dir / "skills"


def _templates_dir() -> Path:
    return Path(__file__).parent / "lib" / "skills"


def _load_skills_cache(claude_dir: Path) -> set:
    global _installed_skills_cache
    if _installed_skills_cache is not None:
        return _installed_skills_cache
    skills_dir = _skills_dir(claude_dir)
    if skills_dir.exists():
        _installed_skills_cache = {f.name for f in skills_dir.glob("check-*-integration.md")}
    else:
        _installed_skills_cache = set()
    return _installed_skills_cache


def _install_skill(claude_dir: Path, template_name: str, skill_name: str) -> bool:
    """Copy a skill template from lib/skills/ to .claude/skills/. Returns True if installed."""
    global _installed_skills_cache
    src = _templates_dir() / template_name
    if not src.exists():
        return False
    dst_dir = _skills_dir(claude_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / skill_name
    dst.write_text(src.read_text())
    if _installed_skills_cache is not None:
        _installed_skills_cache.add(skill_name)
    return True


def _detect_and_install_skills(cwd: Path, content: str) -> None:
    claude_dir = cwd / ".claude"
    if not claude_dir.exists():
        return
    templates_dir = _templates_dir()
    if not templates_dir.exists():
        return
    installed = _load_skills_cache(claude_dir)
    for _name, (pattern, template, skill_file) in INTEGRATION_SKILLS.items():
        if skill_file in installed:
            continue
        if pattern.search(content):
            _install_skill(claude_dir, template, skill_file)


def debug_log(cwd, msg):
    if DEBUG:
        try:
            with open(cwd / ".vibecheck" / "debug.log", "a") as f:
                f.write(f"[post] {msg}\n")
        except Exception:
            pass


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in WATCHED_TOOLS:
        sys.exit(0)

    raw_cwd = Path(hook_input.get("cwd", os.getcwd()))
    cwd = project.find_project_root(raw_cwd)
    if not cwd or not store.is_initialized(cwd):
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    tool_response = hook_input.get("tool_response", "")

    file_path = (
        tool_input.get("file_path") or
        tool_input.get("path") or ""
    )
    if not file_path:
        sys.exit(0)

    # Skip binary/asset files
    if Path(file_path).suffix.lower() in SKIP_EXTENSIONS:
        sys.exit(0)

    # Get content to analyze
    content = ""
    if tool_name == "Read":
        content = tool_response if isinstance(tool_response, str) else str(tool_response)
    elif tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "")
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        content = " ".join(e.get("new_string", "") for e in edits)

    if not content or len(content) < 50:
        sys.exit(0)

    # Make path relative to project root for storage
    try:
        rel_path = str(Path(file_path).relative_to(cwd))
    except ValueError:
        rel_path = file_path

    context_extractor.update_context(store.vg_dir(cwd), rel_path, content)
    debug_log(cwd, f"Extracted context from {rel_path}")

    _detect_and_install_skills(cwd, content)

    # Framework detection — only on writes (not Read) so we know what Claude is changing
    if tool_name in ("Write", "Edit", "MultiEdit"):
        matched = _detect_frameworks(content, file_path)
        if matched:
            _update_active_frameworks(cwd, matched, rel_path)
            debug_log(cwd, f"Frameworks detected: {matched}")

    sys.exit(0)


if __name__ == "__main__":
    main()
