#!/usr/bin/env python3
"""
VibeCheck PostToolUse Hook.

Fires after Read/Write/Edit/MultiEdit tool calls.
Extracts security-relevant project facts into .vibecheck/project_context.json.
Zero LLM calls — pure regex. Must complete in < 100ms.
"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import project, store, context_extractor

DEBUG = os.environ.get("VIBEGUARD_DEBUG") == "1"

WATCHED_TOOLS = {"Read", "Write", "Edit", "MultiEdit"}
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                   ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webp",
                   ".lock", ".sum"}

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
        # tool_response contains the file content
        content = tool_response if isinstance(tool_response, str) else str(tool_response)
    elif tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        # Analyze the new content being written
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
    sys.exit(0)


if __name__ == "__main__":
    main()
