#!/usr/bin/env python3
"""Pre-formats findings for /vibecheck command output. Works from any cwd including worktrees."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import project, store

SEV_ICON  = {"CRITICAL": "🔴", "PITFALL": "⚡", "HYGIENE": "🧹", "GOOD_TO_HAVE": "💡"}
SEV_LABEL = {"CRITICAL": "Critical — fix before shipping", "PITFALL": "Pitfalls",
             "HYGIENE": "Hygiene", "GOOD_TO_HAVE": "Suggestions"}

def rel_path(file_str, cwd):
    if not file_str:
        return None
    parts = file_str.rsplit(":", 1)
    path_str = parts[0]
    line = f":{parts[1]}" if len(parts) > 1 and parts[1].isdigit() else ""
    try:
        return f"{Path(path_str).relative_to(cwd)}{line}"
    except ValueError:
        return f"{path_str}{line}"

def format_finding(f, cwd):
    fid   = f.get("id", "?")
    sev   = f.get("severity", "")
    title = f.get("title", "Untitled")
    icon  = SEV_ICON.get(sev, "•")

    file_str   = f.get("file") or ""
    file_paths = f.get("file_paths") or ([file_str] if file_str else [])
    rel_files  = [rel_path(fp, cwd) for fp in file_paths if fp]

    why     = f.get("why") or f.get("description", "")
    details = f.get("details", "")
    fix     = f.get("fix_prompt", "")

    out = [f"**{fid}** {icon} {title}"]
    if rel_files:
        out.append(f"*{', '.join(r for r in rel_files if r)}*")
    if why:
        out.append(f"\n{why}")
    if details:
        out.append(f"\n{details}")
    if fix:
        out.append(f"\n**Fix** — paste to Claude:\n```\n{fix.strip()}\n```")
    out.append(f"\n`/vibecheck-resolve {fid}` · `/vibecheck-detail {fid}`")
    return "\n".join(out)

def main():
    cwd = project.find_project_root(Path("."))
    if not cwd or not store.is_initialized(cwd):
        print("VibeCheck not initialized. Run: `npx github:playgroundparth/VibeCheck init`")
        return

    findings_path = cwd / ".vibecheck" / "findings.json"
    if not findings_path.exists():
        print("No findings yet. Try `/vibecheck-scan` to run a full scan.")
        return

    all_findings = json.loads(findings_path.read_text())
    if isinstance(all_findings, dict):
        all_findings = all_findings.get("findings", [])

    open_findings = [f for f in all_findings if f.get("status", "open") not in ("resolved", "dismissed")]
    resolved      = [f for f in all_findings if f.get("status") == "resolved"]

    if not open_findings:
        msg = "✅ No open findings."
        if resolved:
            msg += f" ({len(resolved)} previously resolved)"
        print(msg)
        return

    for sev in ["CRITICAL", "PITFALL", "HYGIENE", "GOOD_TO_HAVE"]:
        bucket = [f for f in open_findings if f.get("severity") == sev]
        if not bucket:
            continue
        print(f"## {SEV_ICON[sev]} {SEV_LABEL[sev]}\n")
        for f in bucket:
            print(format_finding(f, cwd))
            print("\n---\n")

    counts = {s: sum(1 for f in open_findings if f.get("severity") == s) for s in SEV_ICON}
    summary = " · ".join(f"{SEV_ICON[s]} {counts[s]}" for s in SEV_ICON if counts[s])
    print(f"**{len(open_findings)} open findings** — {summary}")
    if resolved:
        print(f"✅ {len(resolved)} resolved")

if __name__ == "__main__":
    main()
