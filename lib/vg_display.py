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

def _file_ref(f, cwd):
    file_str = f.get("file") or (f.get("file_paths") or [""])[0]
    r = rel_path(file_str, cwd) if file_str else None
    return f"  *{r}*" if r else ""

def format_critical(f, cwd):
    """CRITICAL: title + file + one-line why + detail hint. Short but informative."""
    fid   = f.get("id", "?")
    title = f.get("title", "Untitled")
    loc   = _file_ref(f, cwd)
    why   = (f.get("why") or f.get("description", "")).split("\n")[0][:140]
    out   = [f"🔴 **{fid}** {title}{loc}"]
    if why:
        out.append(f"   {why}")
    out.append(f"   `/vibecheck {fid}` for fix · `/vibecheck-resolve {fid}`")
    return "\n".join(out)

def format_oneliner(f, cwd):
    """One line: icon + id + title + file. Used for PITFALL, HYGIENE, GOOD_TO_HAVE."""
    fid   = f.get("id", "?")
    sev   = f.get("severity", "")
    title = f.get("title", "Untitled")
    icon  = SEV_ICON.get(sev, "•")
    loc   = _file_ref(f, cwd)
    return f"{icon} **{fid}** {title}{loc}"

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

    # CRITICAL: compact card with one-line why (urgent, but full fix is one step away)
    criticals = [f for f in open_findings if f.get("severity") == "CRITICAL"]
    if criticals:
        print("## 🔴 Fix before shipping\n")
        for f in criticals:
            print(format_critical(f, cwd))
            print()

    # PITFALL, HYGIENE, GOOD_TO_HAVE: one-liners — run /vibecheck <id> for detail
    for sev in ["PITFALL", "HYGIENE", "GOOD_TO_HAVE"]:
        bucket = [f for f in open_findings if f.get("severity") == sev]
        if not bucket:
            continue
        print(f"## {SEV_ICON[sev]} {SEV_LABEL[sev]}\n")
        # GOOD_TO_HAVE: group all IDs on one line to save space
        if sev == "GOOD_TO_HAVE":
            ids = " · ".join(f"**{f.get('id','?')}**" for f in bucket)
            print(f"💡 {ids}")
        else:
            for f in bucket:
                print(format_oneliner(f, cwd))
        print()

    counts = {s: sum(1 for f in open_findings if f.get("severity") == s) for s in SEV_ICON}
    parts  = [f"{SEV_ICON[s]} {counts[s]}" for s in SEV_ICON if counts[s]]
    res    = f" · ✅ {len(resolved)} resolved" if resolved else ""
    print(f"**{len(open_findings)} open** — {' · '.join(parts)}{res}")
    print("Run `/vibecheck <id>` for full detail + fix prompt.")

if __name__ == "__main__":
    main()
