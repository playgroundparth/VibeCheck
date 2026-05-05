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
    return f"*{r}*" if r else ""

def format_full_card(f, cwd):
    """Full card: id + title + file + why paragraph + fix block + resolve/detail links."""
    fid   = f.get("id", "?")
    sev   = f.get("severity", "")
    title = f.get("title", "Untitled")
    icon  = SEV_ICON.get(sev, "•")
    loc   = _file_ref(f, cwd)
    why   = (f.get("why") or f.get("description", "")).strip()
    fix   = (f.get("fix_prompt") or "").strip()

    lines = [f"**{fid}** {icon} {title}"]
    if loc:
        lines.append(loc)
    if why:
        lines.append("")
        lines.append(why)
    if fix:
        lines.append("")
        lines.append("**Fix** — paste to Claude:")
        lines.append(f"```\n{fix}\n```")
    lines.append("")
    lines.append(f"`/vibecheck-resolve {fid}` · `/vibecheck-detail {fid}`")
    return "\n".join(lines)

def format_oneliner(f, cwd):
    """One line: id + icon + title + file. Used for GOOD_TO_HAVE."""
    fid   = f.get("id", "?")
    sev   = f.get("severity", "")
    title = f.get("title", "Untitled")
    icon  = SEV_ICON.get(sev, "•")
    loc   = _file_ref(f, cwd)
    why   = (f.get("why") or f.get("description", "")).split("\n")[0][:120]
    out   = f"**{fid}** {icon} {title}"
    if loc:
        out += f"\n{loc}"
    if why:
        out += f"\n{why}"
    return out

def build_full_report(open_findings, resolved, cwd):
    """Build the complete markdown report string."""
    lines = []
    for sev in ["CRITICAL", "PITFALL", "HYGIENE"]:
        bucket = [f for f in open_findings if f.get("severity") == sev]
        if not bucket:
            continue
        lines.append(f"## {SEV_ICON[sev]} {SEV_LABEL[sev]}\n")
        for f in bucket:
            lines.append(format_full_card(f, cwd))
            lines.append("\n---\n")

    suggestions = [f for f in open_findings if f.get("severity") == "GOOD_TO_HAVE"]
    if suggestions:
        lines.append(f"## {SEV_ICON['GOOD_TO_HAVE']} {SEV_LABEL['GOOD_TO_HAVE']}\n")
        for f in suggestions:
            lines.append(format_oneliner(f, cwd))
            lines.append("")

    counts = {s: sum(1 for f in open_findings if f.get("severity") == s) for s in SEV_ICON}
    parts  = [f"{SEV_ICON[s]} {counts[s]}" for s in SEV_ICON if counts[s]]
    res    = f" · ✅ {len(resolved)} resolved" if resolved else ""
    lines.append(f"**{len(open_findings)} open findings** — {' · '.join(parts)}{res}")
    return "\n".join(lines)

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

    # Always write the full report to a markdown file
    report_path = cwd / ".vibecheck" / "report.md"
    full_report = build_full_report(open_findings, resolved, cwd)
    report_path.write_text(full_report)

    # --- Inline output: short enough for Claude to reproduce verbatim ---

    # CRITICAL: full cards (most urgent — needs immediate context)
    criticals = [f for f in open_findings if f.get("severity") == "CRITICAL"]
    if criticals:
        print("## 🔴 Fix before shipping\n")
        for f in criticals:
            print(format_full_card(f, cwd))
            print("\n---\n")

    # Everything else: count summary only
    counts = {s: sum(1 for f in open_findings if f.get("severity") == s) for s in SEV_ICON}
    non_critical = [(s, counts[s]) for s in ["PITFALL", "HYGIENE", "GOOD_TO_HAVE"] if counts[s]]
    if non_critical:
        parts = " · ".join(f"{SEV_ICON[s]} {n} {SEV_LABEL[s].lower()}" for s, n in non_critical)
        print(f"Also: {parts}")
        print()

    res = f" · ✅ {len(resolved)} resolved" if resolved else ""
    print(f"**{len(open_findings)} open** — {' · '.join(f'{SEV_ICON[s]} {counts[s]}' for s in SEV_ICON if counts[s])}{res}")
    print(f"Full report with fix prompts → `.vibecheck/report.md`")

if __name__ == "__main__":
    main()
