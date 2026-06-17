#!/usr/bin/env python3
"""
VibeCheck PostToolUse Hook.

Fires after Read/Write/Edit/MultiEdit tool calls.
- Extracts security-relevant project facts into .vibecheck/project_context.json.
- Auto-installs integration skill files when relevant code is detected.
- Detects active frameworks and writes .vibecheck/active_frameworks.json.
- Runs detection_engine (sync, <100ms) to produce structured evidence.
- Injects evidence into systemMessage so Claude confirms findings, not detects them.
- Launches async detection subprocess on Enhanced/Pro tiers (non-blocking).

Zero LLM calls in the sync path. Must complete in < 200ms.
"""
import json, os, re, sys, shutil, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import project, store, context_extractor, detection_engine, capability

DEBUG = os.environ.get("VIBECHECK_DEBUG") == "1"

WATCHED_TOOLS = {
    "Read", "Write", "Edit", "MultiEdit", # Claude
    "view_file", "write_to_file", "replace_file_content", "multi_replace_file_content", # Antigravity
    "read_file", "write_file", "apply_patch" # Codex
}
WRITE_TOOLS = {
    "Write", "Edit", "MultiEdit",
    "write_to_file", "replace_file_content", "multi_replace_file_content",
    "write_file", "apply_patch"
}
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
    vc_dir = store.vc_dir(cwd)
    af_path = vc_dir / ACTIVE_FRAMEWORKS_FILE
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


def _skills_dir(app_dir: Path) -> Path:
    return app_dir / "skills"


def _templates_dir() -> Path:
    return Path(__file__).parent / "lib" / "skills"


def _load_skills_cache(app_dir: Path) -> set:
    global _installed_skills_cache
    if _installed_skills_cache is not None:
        return _installed_skills_cache
    skills_dir = _skills_dir(app_dir)
    if skills_dir.exists():
        _installed_skills_cache = {f.name for f in skills_dir.glob("check-*-integration.md")}
    else:
        _installed_skills_cache = set()
    return _installed_skills_cache


def _install_skill(app_dir: Path, template_name: str, skill_name: str) -> bool:
    """Copy a skill template from lib/skills/ to app_dir/skills/. Returns True if installed."""
    global _installed_skills_cache
    src = _templates_dir() / template_name
    if not src.exists():
        return False
    dst_dir = _skills_dir(app_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / skill_name
    dst.write_text(src.read_text())
    if _installed_skills_cache is not None:
        _installed_skills_cache.add(skill_name)
    return True


def _detect_and_install_skills(cwd: Path, content: str, app_dir_name: str) -> None:
    app_dir = cwd / app_dir_name
    if not app_dir.exists():
        return
    templates_dir = _templates_dir()
    if not templates_dir.exists():
        return
    installed = _load_skills_cache(app_dir)
    for _name, (pattern, template, skill_file) in INTEGRATION_SKILLS.items():
        if skill_file in installed:
            continue
        if pattern.search(content):
            _install_skill(app_dir, template, skill_file)


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

    cfg = store.load_config(cwd)
    mode = cfg.get("mode", "full")
    if mode == "off":
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    tool_response = hook_input.get("tool_response", "")

    file_path = (
        tool_input.get("file_path") or
        tool_input.get("path") or
        tool_input.get("TargetFile") or
        tool_input.get("AbsolutePath") or ""
    )
    if not file_path:
        sys.exit(0)

    # Skip binary/asset files
    if Path(file_path).suffix.lower() in SKIP_EXTENSIONS:
        sys.exit(0)

    # Determine absolute and relative paths
    abs_path = Path(file_path) if Path(file_path).is_absolute() else cwd / file_path
    try:
        rel_path = str(abs_path.relative_to(cwd))
    except ValueError:
        rel_path = str(abs_path)

    # Get content to analyze
    content = ""
    if tool_name in ("Read", "view_file", "read_file"):
        content = tool_response if isinstance(tool_response, str) else str(tool_response)
    elif tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "write_to_file":
        content = tool_input.get("CodeContent", "")
    elif tool_name == "write_file":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "")
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        content = " ".join(e.get("new_string", "") for e in edits)
    elif tool_name == "replace_file_content":
        content = tool_input.get("ReplacementContent", "")

    # Disk-read fallback
    if not content and tool_name in WRITE_TOOLS:
        try:
            if abs_path.exists():
                content = abs_path.read_text(errors="ignore")
        except Exception:
            pass

    if not content or len(content) < 50:
        sys.exit(0)

    app_dir_name = Path(__file__).parent.parent.name
    if not app_dir_name.startswith("."):
        # fallback if not installed in a dot-folder structure during testing
        app_dir_name = ".claude"

    context_extractor.update_context(store.vc_dir(cwd), rel_path, content)
    debug_log(cwd, f"Extracted context from {rel_path}")

    _detect_and_install_skills(cwd, content, app_dir_name)

    # Framework detection — only on writes so we know what is changing
    if tool_name in WRITE_TOOLS:
        matched = _detect_frameworks(content, file_path)
        if matched:
            _update_active_frameworks(cwd, matched, rel_path)
            debug_log(cwd, f"Frameworks detected: {matched}")

        # ── Run sync detection engine (<100ms) ─────────────────────────────
        evidence = detection_engine.run(cwd, [abs_path])
        debug_log(cwd, f"Detection engine: {len(evidence)} evidence item(s)")

        # Compute next finding ID
        findings = store.load_findings(cwd)
        next_id = max(
            (int(f["id"].split("-")[1]) for f in findings if f.get("id", "").startswith("vc-") or f.get("id", "").startswith("vg-")),
            default=0
        ) + 1

        # ── Launch async detection if Enhanced/Pro tier and mode is full/pro ──
        tier = capability.detect_tier(cwd)
        async_lock = store.vc_dir(cwd) / "async.lock"
        if mode in ("full", "pro") and tier in ("enhanced", "pro") and not async_lock.exists():
            _launch_async_detection(cwd, [str(abs_path)])
            debug_log(cwd, f"Launched async detection (tier: {tier})")

        # ── Build systemMessage with evidence ──────────────────────────────
        framework_note = ""
        if matched:
            names = ", ".join(sorted(matched))
            framework_note = (
                f"\nFrameworks: {names} — load {app_dir_name}/hooks/lib/frameworks/<name>.md "
                f"for context during your check."
            )

        evidence_block = detection_engine.format_for_injection(evidence, next_id, tier)

        print(json.dumps({
            "systemMessage": (
                f"[VibeCheck] {rel_path} was just modified.{framework_note}\n\n"
                f"{evidence_block}\n\n"
                f"Run the inline check (CLAUDE.md VibeCheck section) and emit the footer before finishing."
            )
        }))

    sys.exit(0)


def _launch_async_detection(cwd: Path, files: list) -> None:
    """Launch async_detection.py as a detached background subprocess."""
    try:
        lib_dir = Path(__file__).parent / "lib"
        async_script = lib_dir / "async_detection.py"
        if not async_script.exists():
            return
        subprocess.Popen(
            [
                sys.executable, str(async_script),
                "--cwd", str(cwd),
                "--files", ",".join(files),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach from hook process
        )
    except Exception:
        pass  # Non-fatal — async detection is optional


if __name__ == "__main__":
    main()
