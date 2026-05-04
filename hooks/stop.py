#!/usr/bin/env python3
"""
VibeCheck Stop Hook.

Runs static checks instantly, logs task completion.
Also emits a lightweight reminder systemMessage in case Claude skipped
the inline VibeCheck analysis required by CLAUDE.md.
"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import store, static_checks, guardrails, project, metrics, telemetry

DEBUG = os.environ.get("VIBEGUARD_DEBUG") == "1"

def debug_log(cwd, msg):
    if DEBUG:
        try:
            with open(cwd / ".vibecheck" / "debug.log", "a") as f:
                f.write(f"[stop] {msg}\n")
        except Exception:
            pass

def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    raw_cwd = Path(hook_input.get("cwd", os.getcwd()))
    cwd = project.find_project_root(raw_cwd)
    if not cwd or not store.is_initialized(cwd):
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "")

    changed_files = get_changed_files_this_turn(transcript_path, cwd)
    changed_files = guardrails.filter_session_files(cwd, changed_files)
    debug_log(cwd, f"Changed files: {len(changed_files)}")

    if not changed_files:
        sys.exit(0)

    # Log task completed
    store.log_event(cwd, {
        "type": "task_completed",
        "files_changed": [str(f) for f in changed_files],
        "file_count": len(changed_files),
        "session_id": session_id,
        "project_id": project.get_project_info(cwd)["id"],
    })
    cfg = telemetry.load_config(cwd)
    try:
        metrics.record_task_completed(cwd)
        telemetry.track_task_completed(cfg)
    except Exception:
        pass

    # Run static checks instantly
    t0 = __import__("time").time()
    static_findings = static_checks.run_static_checks(cwd, changed_files)
    for f in static_findings:
        if not any(x.get("title") == f.get("title") for x in store.load_findings(cwd)):
            store.add_finding(cwd, f)
            store.log_event(cwd, {"type": "finding_added", "finding_id": f["id"],
                                  "severity": f["severity"], "title": f["title"], "source": "static"})
            telemetry.track_finding_added(cfg, f["severity"])
    debug_log(cwd, f"Static: {len(static_findings)} findings in {int(((__import__('time').time()-t0)*1000))}ms")

    # Emit a reminder in case Claude skipped the inline VibeCheck step.
    # If Claude already did VibeCheck (CLAUDE.md followed), it will say so briefly.
    # If Claude missed it, this triggers the analysis on the next response.
    rel_files = []
    for f in changed_files:
        try:
            rel_files.append(str(f.relative_to(cwd)))
        except ValueError:
            rel_files.append(str(f))

    findings = store.load_findings(cwd)
    open_findings = [f for f in findings if f.get("status", "open") == "open"]
    next_id = max((int(f["id"].split("-")[1]) for f in findings if f.get("id","").startswith("vg-")), default=0) + 1

    file_list = "\n".join(f"  • {rf}" for rf in rel_files)
    open_summary = ""
    if open_findings:
        lines = [f"\nOpen findings to re-check: {len(open_findings)}"]
        for f in open_findings[-5:]:
            lines.append(f"  {f['id']} ({f['severity']}): {f['title'][:60]}")
        open_summary = "\n".join(lines)

    msg = f"""[VibeCheck] Files modified this turn:
{file_list}

If you already appended the VibeCheck footer above — you're done, ignore this.
If you didn't — do it now (CLAUDE.md §VibeCheck requires it after every Write/Edit/MultiEdit).

Next finding ID: vg-{next_id:03d}
Findings file: {cwd / '.vibecheck' / 'findings.json'}{open_summary}"""

    print(json.dumps({"systemMessage": msg}))


def get_changed_files_this_turn(transcript_path, cwd):
    if not transcript_path or not Path(transcript_path).exists():
        return []
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except Exception:
        return []

    changed, in_last_turn = [], False
    last_turn_entries = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        entry_type = entry.get("type", "")
        if entry_type == "assistant":
            in_last_turn = True
        if in_last_turn:
            last_turn_entries.append(entry)
        if in_last_turn and entry_type == "user":
            break

    for entry in last_turn_entries:
        content = entry.get("message", {}).get("content") or entry.get("content") or []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Write", "Edit", "MultiEdit"):
                continue
            fp = block.get("input", {}).get("file_path") or block.get("input", {}).get("path", "")
            if fp:
                p = Path(fp) if Path(fp).is_absolute() else cwd / fp
                if p.exists() and p not in changed:
                    changed.append(p)
    return changed


if __name__ == "__main__":
    main()
