#!/usr/bin/env python3
"""
VibeCheck Session Start Hook.
Walks up to find project root. Waits for analyzer. Runs guardrails.
Injects summary into context.
"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import store, guardrails, project, metrics, context_extractor

DEBUG = os.environ.get("VIBECHECK_DEBUG") == "1"
MAX_LOCK_WAIT_SECONDS = 30
LOCK_CHECK_INTERVAL = 0.5

def debug_log(cwd, msg):
    if DEBUG:
        try:
            with open(cwd / ".vibecheck" / "debug.log", "a") as f:
                f.write(f"[start] {msg}\n")
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

    # Wait for analyzer to finish
    if store.is_locked(cwd):
        debug_log(cwd, "Lock present — waiting")
        waited = 0
        while store.is_locked(cwd) and waited < MAX_LOCK_WAIT_SECONDS:
            time.sleep(LOCK_CHECK_INTERVAL)
            waited += LOCK_CHECK_INTERVAL
        debug_log(cwd, f"Lock cleared after {waited}s")
        if store.is_locked(cwd):
            store.release_lock(cwd)
            store.log_event(cwd, {"type": "lock_force_released", "waited_seconds": waited})

    # Run guardrails post-analysis
    snapshot_path = store.vc_dir(cwd) / "source_snapshot.json"
    if snapshot_path.exists():
        try:
            snapshot = json.loads(snapshot_path.read_text())
            findings_before_path = store.vc_dir(cwd) / "findings_before_analyzer.json"
            findings_before = []
            if findings_before_path.exists():
                findings_before = json.loads(findings_before_path.read_text())
            result = guardrails.run_post_analysis_guards(cwd, snapshot, findings_before)
            if result["violations_logged"] > 0:
                debug_log(cwd, f"Guardrail violations: {result}")
            snapshot_path.unlink(missing_ok=True)
            findings_before_path.unlink(missing_ok=True)
        except Exception as e:
            debug_log(cwd, f"Guardrails error: {e}")

    # Sync metrics with timeline (background analyzer can't call metrics directly)
    sync_analyses_from_timeline(cwd)

    # Build context lines
    context_lines = []

    # Async detection results from last session (Semgrep/Gitleaks background run)
    async_results_line = _surface_async_results(cwd)
    if async_results_line:
        context_lines.append(async_results_line)

    # Project context (auth, stack, known risks)
    ctx_summary = context_extractor.summarize(store.vc_dir(cwd))
    if ctx_summary:
        context_lines.append(ctx_summary)

    # Findings summary
    summary = store.load_summary(cwd)
    if summary.get("total_open", 0) > 0:
        context_lines.append(build_summary_line(summary))

    # Recent context log (decisions, preferences, errors resolved)
    context_log_summary = build_context_log_summary(cwd)
    if context_log_summary:
        context_lines.append(context_log_summary)

    if not context_lines:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(context_lines),
        }
    }))
    sys.exit(0)


def sync_analyses_from_timeline(cwd):
    """Reconcile metrics with actual findings.json and timeline.json.
    The LLM analyzer writes directly to these files, bypassing metrics counters."""
    try:
        m = metrics.load_metrics(cwd)
        changed = False

        # Sync analyses_run from timeline
        timeline_path = store.vc_dir(cwd) / "timeline.json"
        if timeline_path.exists():
            timeline = json.loads(timeline_path.read_text())
            analysis_events = [e for e in timeline if e.get("type") == "analysis_run"]
            recorded = m.get("totals", {}).get("analyses_run", 0)
            unrecorded = len(analysis_events) - recorded
            if unrecorded > 0:
                for event in analysis_events[-unrecorded:]:
                    files = event.get("files_analyzed", 10)
                    tokens = files * 2000
                    cost = metrics.compute_cost(tokens, "haiku")
                    m["totals"]["analyses_run"] += 1
                    m["totals"]["tokens_consumed"] += tokens
                    m["totals"]["cost_usd"] = round(m["totals"]["cost_usd"] + cost, 4)
                    day = event.get("ts", "")[:10] or metrics.today_key()
                    if day not in m["by_day"]:
                        m["by_day"][day] = metrics._empty_day()
                    m["by_day"][day]["analyses"] += 1
                    m["by_day"][day]["tokens"] += tokens
                    m["by_day"][day]["cost"] = round(m["by_day"][day].get("cost", 0) + cost, 4)
                changed = True

        # Sync findings_created from findings.json
        findings_path = store.vc_dir(cwd) / "findings.json"
        if findings_path.exists():
            findings = json.loads(findings_path.read_text())
            actual_total = len(findings)
            recorded_total = m.get("totals", {}).get("findings_created", 0)
            if actual_total > recorded_total:
                gap = actual_total - recorded_total
                m["totals"]["findings_created"] = actual_total
                today = metrics.today_key()
                if today not in m["by_day"]:
                    m["by_day"][today] = metrics._empty_day()
                m["by_day"][today]["findings_created"] = m["by_day"][today].get("findings_created", 0) + gap
                changed = True

            # Sync resolved/dismissed counts
            actual_resolved = sum(1 for f in findings if f.get("status") == "resolved")
            actual_dismissed = sum(1 for f in findings if f.get("status") == "dismissed")
            if actual_resolved != m["totals"].get("findings_resolved", 0):
                m["totals"]["findings_resolved"] = actual_resolved
                changed = True
            if actual_dismissed != m["totals"].get("findings_dismissed", 0):
                m["totals"]["findings_dismissed"] = actual_dismissed
                changed = True

        if changed:
            if not m.get("first_seen"):
                m["first_seen"] = metrics.now_iso()
            metrics.save_metrics(cwd, m)

        # Rebuild summary.json from ground truth (analyzer may write stale counts)
        if findings_path.exists():
            findings = json.loads(findings_path.read_text())
            open_f = [f for f in findings if f.get("status") == "open"]
            counts = {}
            for f in open_f:
                sev = f.get("severity", "HYGIENE")
                counts[sev] = counts.get(sev, 0) + 1
            summary = {
                "counts": {
                    "CRITICAL": counts.get("CRITICAL", 0),
                    "PITFALL": counts.get("PITFALL", 0),
                    "HYGIENE": counts.get("HYGIENE", 0),
                    "GOOD_TO_HAVE": counts.get("GOOD_TO_HAVE", 0),
                },
                "total_open": len(open_f),
                "total_all": len(findings),
                "updated_at": metrics.now_iso(),
            }
            store.write_json(store.vc_dir(cwd) / "summary.json", summary)
    except Exception:
        pass


def _surface_async_results(cwd: Path) -> str:
    """
    Surface Semgrep/Gitleaks findings from the last session's background run.
    Reads .vibecheck/async_results.json, returns a context line, then deletes the file.
    Discards results older than 24 hours (stale).
    """
    async_results_path = store.vc_dir(cwd) / "async_results.json"
    if not async_results_path.exists():
        return ""
    try:
        age_seconds = time.time() - async_results_path.stat().st_mtime
        if age_seconds > 86400:  # 24h — discard stale results
            async_results_path.unlink(missing_ok=True)
            return ""
        data = json.loads(async_results_path.read_text())
        results = data.get("results", [])
        async_results_path.unlink(missing_ok=True)  # consume once
        if not results:
            return ""

        lines = []

        # Surface mutation score separately — it's a verdict, not just another finding
        mutation_results = [r for r in results if r.get("source") == "mutation"]
        other_results = [r for r in results if r.get("source") != "mutation"]

        for mr in mutation_results:
            score_pct = mr.get("mutation_score_pct")
            survived = mr.get("mutation_survived")
            tool = mr.get("mutation_tool", "mutation testing")
            if score_pct is not None:
                if score_pct >= 80:
                    icon = "✅"
                elif score_pct >= 50:
                    icon = "⚠️ "
                else:
                    icon = "❌"
                score_line = f"[VibeCheck] {icon} {tool} mutation score: {score_pct}%"
                if survived and survived > 0:
                    score_line += f" — {survived} mutant{'s' if survived != 1 else ''} survived (run `{tool} results` to see which)"
                else:
                    score_line += " — all mutants killed, tests are verifying real behavior"
                lines.append(score_line)
            else:
                lines.append(f"[VibeCheck] {tool} ran after your test changes — check results")

        if other_results:
            n = len(other_results)
            criticals = sum(1 for r in other_results if r.get("suggested_severity") == "CRITICAL")
            sources = sorted({r.get("source", "semgrep") for r in other_results})
            source_str = "+".join(sources)
            sev_str = f"🔴 {criticals} critical" if criticals else f"{n} issue{'s' if n > 1 else ''}"
            lines.append(
                f"[VibeCheck] {sev_str} found by {source_str} background scan (last session). "
                f"Run /vibecheck to review."
            )

        return "\n".join(lines)
    except Exception:
        try:
            async_results_path.unlink(missing_ok=True)
        except Exception:
            pass
        return ""


def build_context_log_summary(cwd):
    """Inject the last N context_log entries so Claude has session continuity."""
    log_path = store.vc_dir(cwd) / "context_log.jsonl"
    if not log_path.exists():
        return ""
    try:
        lines = [l.strip() for l in log_path.read_text().splitlines() if l.strip()]
        if not lines:
            return ""
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        if not entries:
            return ""
        # Show last 5 entries, most recent first
        recent = entries[-5:][::-1]
        parts = []
        for e in recent:
            ts = e.get("ts", "")[:10]  # date only
            etype = e.get("type", "note")
            summary = e.get("summary", "")
            importance = e.get("importance", "")
            tag = f"[{etype}]" + (f"[{importance}]" if importance == "critical" else "")
            parts.append(f"  {ts} {tag} {summary}")
        header = f"[VibeCheck] Last {len(recent)} context note(s) from previous sessions:"
        return header + "\n" + "\n".join(parts)
    except Exception:
        return ""


def build_summary_line(summary):
    counts = summary.get("counts", {})
    critical = counts.get("CRITICAL", 0)
    pitfall  = counts.get("PITFALL", 0)
    hygiene  = counts.get("HYGIENE", 0)
    good     = counts.get("GOOD_TO_HAVE", 0)

    parts = []
    if critical: parts.append(f"🔴 {critical} critical")
    if pitfall:  parts.append(f"⚡ {pitfall} pitfall{'s' if pitfall!=1 else ''}")
    if hygiene:  parts.append(f"🧹 {hygiene} hygiene")
    if good:     parts.append(f"💡 {good} suggestion{'s' if good!=1 else ''}")

    if not parts:
        return ""

    if critical > 0:
        action = "Type `/vibecheck` to review before continuing"
    else:
        action = "Type `/vibecheck` to review (or keep going)"

    return f"[VibeCheck] {' · '.join(parts)} · {action}"


if __name__ == "__main__":
    main()
