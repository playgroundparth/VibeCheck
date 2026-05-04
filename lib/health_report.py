#!/usr/bin/env python3
"""
VibeCheck health report generator.

Generates a static HTML file (.vibeguard/health-report.html) the user can
open in any browser. Shows:
  - Project info
  - Findings dashboard (counts, severity breakdown)
  - Quick wins (high-impact + low-effort)
  - Open findings list with fix prompts
  - Timeline of recent activity
  - Pattern stats

No dependencies, no JS framework. Just HTML + minimal inline CSS.
File is fully self-contained so it works offline.
"""

import json
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

import store
import project as project_lib
import patterns


# ─── Effort/impact derivation ────────────────────────────────────────────────

def derive_effort(finding: Dict) -> str:
    """
    Effort for a vibe coder = risk of Claude getting it wrong without full context,
    NOT lines of code changed. A 3-line fix that requires understanding auth flow =
    medium. A 200-line refactor Claude can do with full repo context = still medium.

    Returns: 'quick' (paste prompt, done), 'medium' (needs a follow-up check),
             'deep' (requires architectural decisions the user must make)
    """
    source = finding.get("source", "")
    tags = set(finding.get("tags", []))
    severity = finding.get("severity", "")

    # Static checks: deterministic, well-understood fixes
    if source == "static":
        return "quick"  # add to .gitignore, rotate key, write README line

    # Pattern-matched: specific enough that fix is mechanical
    if source.startswith("pattern:"):
        return "medium" if severity == "CRITICAL" else "quick"

    # LLM findings: classify by how much context Claude needs to fix safely
    if severity == "CRITICAL":
        # Security fixes touch auth/validation — Claude needs full context to get right
        return "medium"

    if severity == "PITFALL":
        # Architectural changes require the user to choose a direction
        if "reinvention" in tags or "complexity" in tags or "architecture" in tags:
            return "deep"
        return "medium"

    if severity == "HYGIENE":
        # Writing tests needs understanding of what to test — not trivial
        if "testing" in tags:
            return "medium"
        return "quick"

    if severity == "GOOD_TO_HAVE":
        return "quick"

    return "medium"


_SECURITY_KEYWORDS = {"auth", "security", "injection", "traversal", "webhook", "secret",
                      "credential", "xss", "csrf", "privilege", "leak", "exposure"}

def derive_impact(finding: Dict) -> str:
    """Returns: 'high', 'medium', 'low'"""
    severity = finding.get("severity", "")
    tags = set(finding.get("tags", []))
    title_lower = finding.get("title", "").lower()
    why_lower = finding.get("why", "").lower()

    # Security signals in tags or text always = high
    security_hit = bool(tags & _SECURITY_KEYWORDS) or any(
        kw in title_lower or kw in why_lower for kw in _SECURITY_KEYWORDS
    )
    if security_hit:
        return "high"

    if severity == "CRITICAL":
        return "high"
    if severity == "PITFALL":
        return "medium"
    if severity == "HYGIENE":
        return "medium" if "testing" in tags else "low"
    if severity == "GOOD_TO_HAVE":
        return "low"
    return "medium"


def is_praise(finding: Dict) -> bool:
    """Detect GOOD_TO_HAVE findings that are compliments, not improvement suggestions.
    TODO: Replace with a STRENGTH severity in the analyzer prompt so this heuristic
    isn't needed. Keyword matching will misclassify e.g. "comprehensive test suite
    has gaps" (real finding) or "good coverage" (praise that misses the keywords)."""
    if finding.get("severity") != "GOOD_TO_HAVE":
        return False
    praise_words = {"excellent", "robust", "comprehensive", "proper", "no known",
                    "well-structured", "correct", "solid", "clean"}
    title_lower = finding.get("title", "").lower()
    why_lower = finding.get("why", "").lower()
    return any(w in title_lower or w in why_lower for w in praise_words)


def is_quick_win(finding: Dict) -> bool:
    """High impact + quick effort."""
    return derive_impact(finding) in ("high", "medium") and derive_effort(finding) == "quick"


# ─── Report generation ───────────────────────────────────────────────────────

def generate_report(cwd: Path) -> Path:
    """Generate health-report.html. Returns path to the file."""
    report_path = store.vg_dir(cwd) / "health-report.html"

    findings = store.load_findings(cwd)
    all_open = [f for f in findings if f.get("status") == "open"]
    resolved = [f for f in findings if f.get("status") == "resolved"]
    memory = store.load_memory(cwd)
    timeline = store.get_recent_timeline(cwd, n=30)
    proj = project_lib.get_project_info(cwd)
    cfg = store.load_config(cwd)
    all_patterns = patterns.load_all_patterns(cwd)

    # Enrich and split praise from actionable findings
    for f in all_open:
        f["_effort"] = derive_effort(f)
        f["_impact"] = derive_impact(f)
        f["_quick_win"] = is_quick_win(f)
        f["_is_praise"] = is_praise(f)

    open_findings = [f for f in all_open if not f.get("_is_praise")]
    strengths = [f for f in all_open if f.get("_is_praise")]
    quick_wins = [f for f in open_findings if f["_quick_win"]]

    # Build summary from ground truth (not stale summary.json)
    counts = {}
    for f in open_findings:
        sev = f.get("severity", "HYGIENE")
        counts[sev] = counts.get(sev, 0) + 1
    summary = {
        "counts": {
            "CRITICAL": counts.get("CRITICAL", 0),
            "PITFALL": counts.get("PITFALL", 0),
            "HYGIENE": counts.get("HYGIENE", 0),
            "GOOD_TO_HAVE": counts.get("GOOD_TO_HAVE", 0),
        },
        "total_open": len(open_findings),
        "total_all": len(findings),
    }

    html_content = _render_html(
        proj=proj,
        cfg=cfg,
        memory=memory,
        summary=summary,
        open_findings=open_findings,
        quick_wins=quick_wins,
        resolved=resolved,
        strengths=strengths,
        timeline=timeline,
        patterns=all_patterns,
    )

    try:
        report_path.write_text(html_content, encoding="utf-8")
    except Exception:
        pass

    return report_path


# ─── HTML rendering ──────────────────────────────────────────────────────────

def _render_html(proj, cfg, memory, summary, open_findings, quick_wins,
                 resolved, strengths, timeline, patterns) -> str:
    counts = summary.get("counts", {})
    now = datetime.now(timezone.utc).isoformat()

    # Effort/impact summary
    effort_summary = {"quick": 0, "medium": 0, "deep": 0}
    for f in open_findings:
        effort_summary[f.get("_effort", "medium")] += 1

    # Group findings by severity
    by_severity = {"CRITICAL": [], "PITFALL": [], "HYGIENE": [], "GOOD_TO_HAVE": []}
    for f in open_findings:
        sev = f.get("severity", "GOOD_TO_HAVE")
        if sev in by_severity:
            by_severity[sev].append(f)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VibeCheck · {html.escape(proj['name'])}</title>
<style>
  :root {{
    --bg: #0d1117;
    --bg-card: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #7d8590;
    --critical: #f85149;
    --pitfall: #d29922;
    --hygiene: #58a6ff;
    --good: #56d364;
    --quick-win: #f0883e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text); margin: 0;
    line-height: 1.5; font-size: 14px;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
  h1, h2, h3 {{ margin: 0 0 12px 0; font-weight: 600; }}
  h1 {{ font-size: 24px; }}
  h2 {{ font-size: 18px; margin-top: 28px; }}
  h3 {{ font-size: 14px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
  header {{ border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }}
  header .meta {{ color: var(--text-muted); font-size: 13px; margin-top: 4px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 16px 0 24px; }}
  .stat {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }}
  .stat-num {{ font-size: 28px; font-weight: 700; }}
  .stat-label {{ color: var(--text-muted); font-size: 12px; margin-top: 2px; }}
  .stat.critical .stat-num {{ color: var(--critical); }}
  .stat.pitfall .stat-num {{ color: var(--pitfall); }}
  .stat.hygiene .stat-num {{ color: var(--hygiene); }}
  .stat.good .stat-num {{ color: var(--good); }}
  .finding {{
    background: var(--bg-card); border: 1px solid var(--border);
    border-left: 3px solid var(--border); border-radius: 6px;
    padding: 14px 16px; margin: 10px 0;
  }}
  .finding.critical {{ border-left-color: var(--critical); }}
  .finding.pitfall {{ border-left-color: var(--pitfall); }}
  .finding.hygiene {{ border-left-color: var(--hygiene); }}
  .finding.good_to_have {{ border-left-color: var(--good); }}
  .finding.quick-win {{ border-left-color: var(--quick-win); border-left-width: 4px; }}
  .finding-title {{ font-weight: 600; margin-bottom: 4px; }}
  .finding-meta {{ font-size: 12px; color: var(--text-muted); margin-bottom: 8px; display: flex; gap: 12px; flex-wrap: wrap; }}
  .finding-meta .tag {{
    background: rgba(255,255,255,0.05); padding: 1px 8px; border-radius: 12px;
    font-size: 11px;
  }}
  .finding-meta .tag.effort-quick {{ color: var(--good); }}
  .finding-meta .tag.effort-medium {{ color: var(--pitfall); }}
  .finding-meta .tag.effort-deep {{ color: var(--critical); }}
  .finding-meta .tag.qw {{ background: var(--quick-win); color: #000; font-weight: 600; }}
  .finding-why {{ color: var(--text-muted); margin: 6px 0 10px; }}
  .finding-fix {{
    background: #0d1117; border: 1px solid var(--border); border-radius: 4px;
    padding: 10px 12px; font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-size: 12px; white-space: pre-wrap; word-break: break-word;
  }}
  .finding-fix-label {{ font-size: 11px; color: var(--text-muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .timeline-item {{ display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; }}
  .timeline-item:last-child {{ border-bottom: none; }}
  .timeline-time {{ color: var(--text-muted); white-space: nowrap; min-width: 130px; font-size: 12px; }}
  .timeline-event {{ flex: 1; }}
  .empty-state {{ color: var(--text-muted); font-style: italic; padding: 20px; text-align: center; }}
  code {{ background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  .stack-list {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .stack-item {{ background: var(--bg-card); border: 1px solid var(--border); padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
  details {{ margin: 8px 0; }}
  summary {{ cursor: pointer; color: var(--text-muted); font-size: 13px; }}
  summary:hover {{ color: var(--text); }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🛡️ VibeCheck · {html.escape(proj['name'])}</h1>
    <div class="meta">
      Project ID: <code>{html.escape(proj['id'])}</code>
      &nbsp;·&nbsp; Branch: <code>{html.escape(proj.get('git_branch') or 'no-git')}</code>
      &nbsp;·&nbsp; Generated: {now}
      &nbsp;·&nbsp; Model: {html.escape(cfg.get('model', 'haiku'))}
    </div>
  </header>

  <h2>Health snapshot</h2>
  <div class="stats">
    <div class="stat critical"><div class="stat-num">{counts.get('CRITICAL', 0)}</div><div class="stat-label">Critical</div></div>
    <div class="stat pitfall"><div class="stat-num">{counts.get('PITFALL', 0)}</div><div class="stat-label">Pitfalls</div></div>
    <div class="stat hygiene"><div class="stat-num">{counts.get('HYGIENE', 0)}</div><div class="stat-label">Hygiene</div></div>
    <div class="stat good"><div class="stat-num">{counts.get('GOOD_TO_HAVE', 0)}</div><div class="stat-label">Suggestions</div></div>
    <div class="stat"><div class="stat-num">{len(quick_wins)}</div><div class="stat-label">⚡ Quick wins</div></div>
    <div class="stat"><div class="stat-num">{len(resolved)}</div><div class="stat-label">✓ Resolved</div></div>
  </div>

  <div class="meta">
    Effort to clear all: <strong>{effort_summary['quick']}</strong> quick (paste fix, done) ·
    <strong>{effort_summary['medium']}</strong> medium (needs a review after) ·
    <strong>{effort_summary['deep']}</strong> deep (you choose the direction)
  </div>

  {_render_project_section(memory)}
  {_render_quick_wins_section(quick_wins) if quick_wins else ''}
  {_render_findings_section('🔴 Critical', 'critical', by_severity['CRITICAL'])}
  {_render_findings_section('⚡ Pitfalls', 'pitfall', by_severity['PITFALL'])}
  {_render_findings_section('🧹 Hygiene', 'hygiene', by_severity['HYGIENE'])}
  {_render_findings_section('💡 Good to have', 'good_to_have', by_severity['GOOD_TO_HAVE'])}
  {_render_strengths_section(strengths)}
  {_render_timeline_section(timeline)}
  {_render_patterns_section(patterns)}
</div>
</body>
</html>"""


def _render_project_section(memory: Dict) -> str:
    proj = memory.get("project", {})
    stack = memory.get("stack", [])
    features = memory.get("features", [])

    if not proj and not stack and not features:
        return ""

    parts = ['<h2>Project</h2>']
    if proj.get("description"):
        parts.append(f'<p>{html.escape(proj["description"])}</p>')
    if proj.get("type"):
        parts.append(f'<p class="meta">Type: {html.escape(proj["type"])}</p>')
    if stack:
        items = ''.join(f'<span class="stack-item">{html.escape(s)}</span>' for s in stack[:30])
        parts.append(f'<h3>Stack</h3><div class="stack-list">{items}</div>')
    if features:
        items = ''.join(f'<li>{html.escape(f)}</li>' for f in features[:30])
        parts.append(f'<h3>Features</h3><ul>{items}</ul>')
    return ''.join(parts)


def _render_quick_wins_section(wins: List[Dict]) -> str:
    if not wins:
        return ""
    parts = ['<h2>⚡ Quick wins</h2>']
    parts.append('<p class="meta">High impact, paste-and-done. Full detail in the section below.</p>')
    for f in wins[:10]:
        fid = html.escape(f.get("id", ""))
        title = html.escape(f.get("title", ""))
        effort = f.get("_effort", "")
        impact = f.get("_impact", "")
        sev = f.get("severity", "").lower()
        parts.append(
            f'<a href="#{fid}" style="text-decoration:none">'
            f'<div class="finding {sev} quick-win" style="display:flex;align-items:center;gap:12px;padding:10px 14px">'
            f'<span class="tag qw" style="white-space:nowrap">QUICK WIN</span>'
            f'<span class="finding-title" style="margin:0">{fid} · {title}</span>'
            f'<span class="tag effort-{effort}" style="margin-left:auto;white-space:nowrap">effort: {effort} · impact: {impact}</span>'
            f'</div></a>'
        )
    return ''.join(parts)


def _render_strengths_section(strengths: List[Dict]) -> str:
    if not strengths:
        return ""
    parts = ['<h2>✅ What\'s working well</h2>']
    parts.append('<p class="meta">These aren\'t problems — the analyzer flagged them as strengths.</p>')
    for f in strengths:
        title_text = html.escape(f.get("title", ""))
        why_text = _render_markdown_text(f.get("why", ""))
        parts.append(f'<div class="finding good_to_have" style="border-left-color:#56d364">'
                     f'<div class="finding-title">{html.escape(f.get("id",""))} · {title_text}</div>'
                     f'<div class="finding-why">{why_text}</div></div>')
    return ''.join(parts)


def _render_findings_section(title: str, css_class: str, findings: List[Dict]) -> str:
    if not findings:
        return ""
    parts = [f'<h2>{title} ({len(findings)})</h2>']
    for f in findings:
        parts.append(_render_finding(f))
    return ''.join(parts)


def _render_markdown_text(text: str) -> str:
    """Render plain markdown-ish text to safe HTML. Handles code blocks and newlines."""
    import re
    # Split on fenced code blocks first
    parts = re.split(r'```(?:\w+)?\n?(.*?)```', text, flags=re.DOTALL)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Code block
            out.append(f'<pre><code>{html.escape(part.strip())}</code></pre>')
        else:
            # Regular text — escape then convert newlines to <br>
            escaped = html.escape(part)
            # Bold: **text**
            escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
            out.append(escaped.replace('\n', '<br>'))
    return ''.join(out)


def _render_finding(f: Dict, quick_win: bool = False) -> str:
    sev = f.get("severity", "GOOD_TO_HAVE").lower()
    classes = f"finding {sev}"
    if quick_win or f.get("_quick_win"):
        classes += " quick-win"

    impact = f.get("_impact", "")
    effort = f.get("_effort", "")

    tags_html = []
    if f.get("_quick_win"):
        tags_html.append('<span class="tag qw">QUICK WIN</span>')
    if effort:
        tags_html.append(f'<span class="tag effort-{effort}">effort: {effort}</span>')
    if impact:
        tags_html.append(f'<span class="tag">impact: {impact}</span>')
    if f.get("file"):
        tags_html.append(f'<span class="tag">📄 {html.escape(f["file"])}</span>')

    fix = f.get("fix_prompt", "")
    details = f.get("details", "")

    details_block = ""
    if details:
        details_block = f"""<details>
            <summary>More detail</summary>
            <div class="finding-why">{_render_markdown_text(details)}</div>
        </details>"""

    fid = html.escape(f.get("id", ""))
    return f"""<div class="{classes}" id="{fid}">
        <div class="finding-title">{fid} · {html.escape(f.get('title', ''))}</div>
        <div class="finding-meta">{''.join(tags_html)}</div>
        <div class="finding-why">{_render_markdown_text(f.get('why', ''))}</div>
        {details_block}
        <div class="finding-fix-label">Fix · paste this into Claude</div>
        <div class="finding-fix">{_render_markdown_text(fix)}</div>
    </div>"""


def _render_timeline_section(timeline: List[Dict]) -> str:
    if not timeline:
        return ""
    parts = ['<h2>Recent activity</h2>']
    EMOJI = {
        "task_completed": "📦",
        "finding_added": "⚠️",
        "finding_resolved": "✅",
        "decision_made": "🏗️",
        "scan_run": "🔍",
        "model_changed": "⚙️",
        "analysis_run": "🔍",
        "pattern_created": "🧬",
        "pattern_promoted": "⬆️",
        "pattern_demoted": "⬇️",
        "pattern_killed": "💀",
        "guardrail_violation": "🚫",
        "installed": "🛡️",
    }
    for entry in reversed(timeline[-30:]):
        ts = entry.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ts_short = dt.strftime("%b %d  %H:%M")
        except Exception:
            ts_short = ts[:16]
        emoji = EMOJI.get(entry.get("type", ""), "·")
        desc = _describe_event(entry)
        parts.append(f"""<div class="timeline-item">
            <div class="timeline-time">{html.escape(ts_short)}</div>
            <div class="timeline-event">{emoji} {html.escape(desc)}</div>
        </div>""")
    return ''.join(parts)


def _describe_event(entry: Dict) -> str:
    t = entry.get("type", "")
    if t == "task_completed":
        n = entry.get("file_count", 0)
        return f"Task completed — {n} file{'s' if n != 1 else ''} changed"
    if t == "finding_added":
        return f"{entry.get('severity', '')}: {entry.get('title', '')}"
    if t == "finding_resolved":
        return f"Resolved {entry.get('finding_id', '')}"
    if t == "decision_made":
        return f"Decision: {entry.get('what', '')}"
    if t == "scan_run":
        return f"Scan ran — {entry.get('findings_added', 0)} findings added"
    if t == "model_changed":
        return f"Model changed to {entry.get('model', '')}"
    if t == "analysis_run":
        return f"Analysis run — {entry.get('findings_added', 0)} findings, {entry.get('files_analyzed', 0)} files"
    if t == "pattern_created":
        return f"Pattern proposed: {entry.get('name', '')}"
    if t == "pattern_promoted":
        return f"Pattern promoted: {entry.get('name', '')} → {entry.get('to', '')}"
    if t == "pattern_killed":
        return f"Pattern killed: {entry.get('name', '')} ({entry.get('reason', '')})"
    if t == "guardrail_violation":
        return f"⚠️ Guardrail: {entry.get('reason', '')}"
    if t == "installed":
        return f"VibeCheck installed (v{entry.get('version', '')})"
    return t


def _render_patterns_section(all_patterns: List[Dict]) -> str:
    active = [p for p in all_patterns if p.get("status") == "active"]
    if not active:
        return ""
    high = [p for p in active if p.get("confidence") == "high"]
    low = [p for p in active if p.get("confidence") == "low"]
    candidates = [p for p in active if p.get("confidence") == "candidate"]

    parts = ['<h2>Learned patterns</h2>']
    parts.append(f'<p class="meta">VibeCheck learns reusable checks from your project. {len(high)} battle-tested · {len(low)} working · {len(candidates)} candidate.</p>')
    for p in active[:20]:
        conf = p.get("confidence", "")
        fires = p.get("times_fired", 0)
        parts.append(f"""<div class="finding hygiene">
            <div class="finding-title">{html.escape(p.get('name', ''))} <span class="tag">{html.escape(conf)}</span></div>
            <div class="finding-why">{html.escape(p.get('description', ''))}</div>
            <div class="meta">Fired {fires}× · created {p.get('created_at', '')[:10]}</div>
        </div>""")
    return ''.join(parts)
