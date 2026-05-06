#!/usr/bin/env python3
"""Pre-formats findings for /vibecheck command output. Works from any cwd including worktrees."""
import json, sys, html as html_lib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import project, store

SEV_ICON  = {"CRITICAL": "🔴", "PITFALL": "⚡", "HYGIENE": "🧹", "GOOD_TO_HAVE": "💡"}
SEV_LABEL = {"CRITICAL": "Critical — fix before shipping", "PITFALL": "Pitfalls",
             "HYGIENE": "Hygiene", "GOOD_TO_HAVE": "Suggestions"}
SEV_COLOR = {"CRITICAL": "#ef4444", "PITFALL": "#f59e0b", "HYGIENE": "#3b82f6", "GOOD_TO_HAVE": "#8b5cf6"}
SEV_BG    = {"CRITICAL": "#1f1010", "PITFALL": "#1c1608", "HYGIENE": "#0f1626", "GOOD_TO_HAVE": "#130f1f"}

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

def _file_ref_plain(f, cwd):
    file_str = f.get("file") or (f.get("file_paths") or [""])[0]
    r = rel_path(file_str, cwd) if file_str else None
    return r or ""

# ── Inline (chat) formatters ────────────────────────────────────────────────

def format_full_card(f, cwd):
    """Full verbose card — used inline for CRITICAL."""
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
    """Single line — used inline for PITFALL / HYGIENE."""
    fid  = f.get("id", "?")
    sev  = f.get("severity", "")
    icon = SEV_ICON.get(sev, "•")
    title = f.get("title", "Untitled")
    loc  = _file_ref(f, cwd)
    return f"{icon} **{fid}** {title}  {loc}".rstrip()

# ── HTML report ─────────────────────────────────────────────────────────────

def _h(s):
    return html_lib.escape(str(s))

def _html_card(f, cwd):
    fid   = f.get("id", "?")
    sev   = f.get("severity", "HYGIENE")
    title = f.get("title", "Untitled")
    loc   = _file_ref_plain(f, cwd)
    why   = (f.get("why") or f.get("description", "")).strip()
    fix   = (f.get("fix_prompt") or "").strip()
    icon  = SEV_ICON.get(sev, "•")
    color = SEV_COLOR.get(sev, "#888")
    bg    = SEV_BG.get(sev, "#111")

    loc_html = f'<div class="file">{_h(loc)}</div>' if loc else ""
    why_html = f'<p class="why">{_h(why)}</p>' if why else ""
    fix_html = f'''
      <div class="fix-label">Fix — paste to Claude:</div>
      <pre class="fix"><code>{_h(fix)}</code></pre>''' if fix else ""
    return f'''
  <div class="card" style="border-left-color:{color};background:{bg}">
    <div class="card-header">
      <span class="badge" style="color:{color}">{_h(icon)} {_h(sev)}</span>
      <span class="fid">{_h(fid)}</span>
    </div>
    <div class="title">{_h(title)}</div>
    {loc_html}
    {why_html}
    {fix_html}
    <div class="actions">
      <code>/vibecheck-resolve {_h(fid)}</code>
      <code>/vibecheck-detail {_h(fid)}</code>
    </div>
  </div>'''

def build_html(open_findings, resolved, cwd, project_name=""):
    counts = {s: sum(1 for f in open_findings if f.get("severity") == s) for s in SEV_ICON}
    badge_parts = " &nbsp; ".join(
        f'<span style="color:{SEV_COLOR[s]}">{SEV_ICON[s]} {counts[s]} {SEV_LABEL[s]}</span>'
        for s in SEV_ICON if counts[s]
    )
    res_note = f'<span style="color:#22c55e">✅ {len(resolved)} resolved</span>' if resolved else ""

    sections = []
    for sev in ["CRITICAL", "PITFALL", "HYGIENE", "GOOD_TO_HAVE"]:
        bucket = [f for f in open_findings if f.get("severity") == sev]
        if not bucket:
            continue
        cards = "\n".join(_html_card(f, cwd) for f in bucket)
        sections.append(f'''
<section>
  <h2 style="color:{SEV_COLOR[sev]}">{SEV_ICON[sev]} {SEV_LABEL[sev]}</h2>
  {cards}
</section>''')

    sections_html = "\n".join(sections)
    title_str = f"VibeCheck — {_h(project_name)}" if project_name else "VibeCheck Report"

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_str}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0d0d0d; color: #e5e5e5; padding: 24px; line-height: 1.5; }}
  h1   {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 24px; }}
  h2   {{ font-size: 0.9rem; font-weight: 600; text-transform: uppercase;
           letter-spacing: .06em; margin: 28px 0 12px; }}
  .card {{ border-left: 3px solid; border-radius: 6px; padding: 14px 16px;
           margin-bottom: 12px; }}
  .card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }}
  .badge {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: .05em; }}
  .fid  {{ font-size: 0.75rem; color: #666; font-family: monospace; }}
  .title {{ font-weight: 600; font-size: 0.95rem; margin-bottom: 4px; }}
  .file  {{ font-family: monospace; font-size: 0.78rem; color: #888; margin-bottom: 8px; }}
  .why   {{ font-size: 0.88rem; color: #ccc; margin-bottom: 10px; }}
  .fix-label {{ font-size: 0.75rem; color: #888; margin-bottom: 4px; margin-top: 8px; }}
  pre.fix {{ background: #111; border: 1px solid #222; border-radius: 4px;
             padding: 10px 12px; font-size: 0.8rem; overflow-x: auto;
             white-space: pre-wrap; word-break: break-word; margin-bottom: 10px; }}
  .actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }}
  .actions code {{ background: #1a1a1a; border: 1px solid #333; border-radius: 4px;
                   padding: 2px 8px; font-size: 0.8rem; color: #aaa; cursor: pointer; }}
  .actions code:hover {{ border-color: #555; color: #fff; }}
  .summary {{ color: #888; font-size: 0.85rem; margin-top: 32px; padding-top: 16px;
              border-top: 1px solid #222; }}
</style>
</head>
<body>
<h1>{title_str}</h1>
<div class="subtitle">{badge_parts} &nbsp; {res_note}</div>
{sections_html}
<div class="summary">{len(open_findings)} open findings · generated by VibeCheck</div>
</body>
</html>'''

# ── Main ─────────────────────────────────────────────────────────────────────

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

    # Always write the HTML report (serves via the vibecheck-report preview server)
    try:
        cfg = json.loads((cwd / ".vibecheck" / "config.json").read_text())
        project_name = cfg.get("project_name", "")
    except Exception:
        project_name = ""

    html_out = build_html(open_findings, resolved, cwd, project_name)
    (cwd / ".vibecheck" / "report.html").write_text(html_out)

    # ── Inline chat output ────────────────────────────────────────────────────

    # CRITICAL: full verbose cards
    criticals = [f for f in open_findings if f.get("severity") == "CRITICAL"]
    if criticals:
        print("## 🔴 Fix before shipping\n")
        for f in criticals:
            print(format_full_card(f, cwd))
            print("\n---\n")

    # PITFALL + HYGIENE: one-liners
    for sev in ["PITFALL", "HYGIENE"]:
        bucket = [f for f in open_findings if f.get("severity") == sev]
        if not bucket:
            continue
        print(f"## {SEV_ICON[sev]} {SEV_LABEL[sev]}\n")
        for f in bucket:
            print(format_oneliner(f, cwd))
        print()

    # GOOD_TO_HAVE: all IDs on one line
    suggestions = [f for f in open_findings if f.get("severity") == "GOOD_TO_HAVE"]
    if suggestions:
        ids = " · ".join(f"**{f.get('id','?')}**" for f in suggestions)
        print(f"## 💡 Suggestions\n\n💡 {ids}\n")

    counts = {s: sum(1 for f in open_findings if f.get("severity") == s) for s in SEV_ICON}
    parts  = " · ".join(f"{SEV_ICON[s]} {counts[s]}" for s in SEV_ICON if counts[s])
    res    = f" · ✅ {len(resolved)} resolved" if resolved else ""
    print(f"**{len(open_findings)} open** — {parts}{res}")
    print("Full report with fix prompts → open the VibeCheck preview panel")

if __name__ == "__main__":
    main()
