#!/usr/bin/env python3
"""
VibeCheck metrics.

Tracks measurable signals so you can answer "is this actually working?":

  Cost metrics:
    - Tokens consumed per run (Haiku → cost in $)
    - Total cost since install
    - Cost trajectory (last 7 days)

  Quality metrics:
    - Findings created per analysis (raw output)
    - Findings resolved (user took action — strongest signal)
    - Findings dismissed (user marked false positive — anti-signal)
    - Resolution rate = resolved / (resolved + dismissed + open)
    - Time-to-resolution (how long findings stay open)

  Performance metrics:
    - Analyzer latency (start → finish)
    - Static check latency
    - Hook overhead

  Usage metrics:
    - Sessions VibeCheck ran in
    - Tasks completed
    - /vg invocations (user actually looked)

Stored in .vibeguard/metrics.json. Fully local.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import store


METRICS_VERSION = 1


def metrics_path(cwd: Path) -> Path:
    return store.vg_dir(cwd) / "metrics.json"


def load_metrics(cwd: Path) -> Dict:
    """Load metrics, return empty structure if missing."""
    return store.read_json(metrics_path(cwd), default={
        "version": METRICS_VERSION,
        "totals": {
            "analyses_run": 0,
            "static_checks_run": 0,
            "tokens_consumed": 0,
            "cost_usd": 0.0,
            "findings_created": 0,
            "findings_resolved": 0,
            "findings_dismissed": 0,
            "vg_invocations": 0,  # user typed /vg
            "tasks_completed": 0,
            "sessions": 0,
        },
        "by_day": {},  # "YYYY-MM-DD": {analyses, tokens, cost, findings_created, ...}
        "latencies": {
            "analyzer_ms": [],     # rolling list of last 100
            "static_check_ms": [],
            "hook_overhead_ms": [],
        },
        "first_seen": None,
        "last_updated": None,
    })


def save_metrics(cwd: Path, metrics: Dict) -> bool:
    metrics["last_updated"] = now_iso()
    return store.write_json(metrics_path(cwd), metrics)


# ─── Recording events ────────────────────────────────────────────────────────

def record_analysis_run(cwd: Path, tokens: int, model: str, latency_ms: int = 0):
    """Record a completed LLM analysis run."""
    cost = compute_cost(tokens, model)

    m = load_metrics(cwd)
    if not m.get("first_seen"):
        m["first_seen"] = now_iso()

    m["totals"]["analyses_run"] += 1
    m["totals"]["tokens_consumed"] += tokens
    m["totals"]["cost_usd"] = round(m["totals"]["cost_usd"] + cost, 4)

    today = today_key()
    if today not in m["by_day"]:
        m["by_day"][today] = _empty_day()
    m["by_day"][today]["analyses"] += 1
    m["by_day"][today]["tokens"] += tokens
    m["by_day"][today]["cost"] = round(m["by_day"][today]["cost"] + cost, 4)

    if latency_ms > 0:
        m["latencies"]["analyzer_ms"].append(latency_ms)
        m["latencies"]["analyzer_ms"] = m["latencies"]["analyzer_ms"][-100:]

    save_metrics(cwd, m)


def record_static_check_run(cwd: Path, latency_ms: int, findings_added: int):
    """Track static check completion. findings_added is informational only;
    actual finding count is bumped by record_finding_added in store.py."""
    m = load_metrics(cwd)
    m["totals"]["static_checks_run"] += 1
    today = today_key()
    if today not in m["by_day"]:
        m["by_day"][today] = _empty_day()
    m["by_day"][today]["static_runs"] += 1
    m["latencies"]["static_check_ms"].append(latency_ms)
    m["latencies"]["static_check_ms"] = m["latencies"]["static_check_ms"][-100:]
    save_metrics(cwd, m)


def record_finding_added(cwd: Path):
    """Called when any finding is added (static, pattern, or LLM)."""
    m = load_metrics(cwd)
    m["totals"]["findings_created"] += 1
    today = today_key()
    if today not in m["by_day"]:
        m["by_day"][today] = _empty_day()
    m["by_day"][today]["findings_created"] += 1
    save_metrics(cwd, m)


def record_finding_resolved(cwd: Path, was_false_positive: bool = False):
    """User marked a finding resolved or dismissed."""
    m = load_metrics(cwd)
    if was_false_positive:
        m["totals"]["findings_dismissed"] += 1
    else:
        m["totals"]["findings_resolved"] += 1
    today = today_key()
    if today not in m["by_day"]:
        m["by_day"][today] = _empty_day()
    if was_false_positive:
        m["by_day"][today]["dismissed"] += 1
    else:
        m["by_day"][today]["resolved"] += 1
    save_metrics(cwd, m)


def record_vg_invocation(cwd: Path):
    """User typed /vg — strongest signal of engagement."""
    m = load_metrics(cwd)
    m["totals"]["vg_invocations"] += 1
    today = today_key()
    if today not in m["by_day"]:
        m["by_day"][today] = _empty_day()
    m["by_day"][today]["vg_invocations"] += 1
    save_metrics(cwd, m)


def record_task_completed(cwd: Path):
    m = load_metrics(cwd)
    m["totals"]["tasks_completed"] += 1
    today = today_key()
    if today not in m["by_day"]:
        m["by_day"][today] = _empty_day()
    m["by_day"][today]["tasks"] += 1
    save_metrics(cwd, m)


def record_hook_overhead(cwd: Path, hook_name: str, latency_ms: int):
    m = load_metrics(cwd)
    m["latencies"]["hook_overhead_ms"].append({"hook": hook_name, "ms": latency_ms})
    m["latencies"]["hook_overhead_ms"] = m["latencies"]["hook_overhead_ms"][-100:]
    save_metrics(cwd, m)


# ─── Reporting (used by /vg-status and the health report) ────────────────────

def get_summary(cwd: Path) -> Dict:
    """High-level summary for status display."""
    m = load_metrics(cwd)
    totals = m.get("totals", {})

    # Read findings ground truth directly — totals drift when analyzer writes findings
    # without going through store.add_finding() (which calls record_finding_added).
    findings_path = store.vg_dir(cwd) / "findings.json"
    try:
        findings = store.read_json(findings_path, default=[])
        for f in findings:
            if f.get("status") is None:
                f["status"] = "open"
        created = len(findings)
        resolved = sum(1 for f in findings if f.get("status") == "resolved")
        dismissed = sum(1 for f in findings if f.get("status") == "dismissed")
        open_count = sum(1 for f in findings if f.get("status") == "open")
    except Exception:
        resolved = totals.get("findings_resolved", 0)
        dismissed = totals.get("findings_dismissed", 0)
        created = totals.get("findings_created", 0)
        open_count = max(0, created - resolved - dismissed)

    if created > 0:
        resolution_rate = resolved / created
        false_positive_rate = dismissed / created
    else:
        resolution_rate = 0.0
        false_positive_rate = 0.0

    # Engagement: vg_invocations / tasks_completed = how often user actually looks
    tasks = totals.get("tasks_completed", 0)
    invocations = totals.get("vg_invocations", 0)
    engagement_rate = invocations / tasks if tasks > 0 else 0.0

    # Last 7 days
    by_day = m.get("by_day", {})
    last_7_keys = _last_n_day_keys(7)
    last_7_cost = sum(by_day.get(k, {}).get("cost", 0) for k in last_7_keys)
    last_7_analyses = sum(by_day.get(k, {}).get("analyses", 0) for k in last_7_keys)

    # Avg latency
    analyzer_lat = m.get("latencies", {}).get("analyzer_ms", [])
    avg_analyzer_ms = sum(analyzer_lat) / len(analyzer_lat) if analyzer_lat else 0

    return {
        "total_cost_usd": totals.get("cost_usd", 0),
        "total_analyses": totals.get("analyses_run", 0),
        "total_findings": created,
        "open_findings": open_count,
        "resolved": resolved,
        "dismissed": dismissed,
        "resolution_rate": round(resolution_rate, 3),
        "false_positive_rate": round(false_positive_rate, 3),
        "engagement_rate": round(engagement_rate, 3),
        "vg_invocations": invocations,
        "tasks_completed": tasks,
        "last_7_days_cost": round(last_7_cost, 4),
        "last_7_days_analyses": last_7_analyses,
        "avg_analyzer_latency_ms": int(avg_analyzer_ms),
        "first_seen": m.get("first_seen"),
        "days_active": _count_active_days(by_day),
    }


def health_signals(cwd: Path) -> Dict:
    """
    Computes 'is VibeCheck actually working?' signals.
    These are the metrics you'd watch over a week of use.
    """
    summary = get_summary(cwd)

    signals = {}

    # Cost sanity: if nothing has run, that's a red flag
    if summary["total_analyses"] == 0:
        signals["status"] = "not_running"
        signals["message"] = "VibeCheck hasn't run yet. After your next task with file changes, it should fire."
        return signals

    # False positive rate: if >40%, the tool is noisy
    fp_rate = summary["false_positive_rate"]
    if fp_rate > 0.4:
        signals["false_positive_warning"] = (
            f"{int(fp_rate*100)}% of findings dismissed — VibeCheck is generating too much noise. "
            f"Consider switching to Sonnet (/vg-model sonnet) for higher quality findings."
        )

    # Engagement: if user runs many tasks but never types /vg, the summary line isn't working
    if summary["tasks_completed"] > 5 and summary["engagement_rate"] < 0.1:
        signals["engagement_warning"] = (
            f"You've completed {summary['tasks_completed']} tasks but only opened /vg "
            f"{summary['vg_invocations']} times. Either nothing is being flagged, or the "
            f"summary line is being missed."
        )

    # Resolution rate: positive signal — findings are actionable
    if summary["resolution_rate"] > 0.3:
        signals["resolution_signal"] = (
            f"Good signal: {int(summary['resolution_rate']*100)}% of findings have been resolved. "
            f"VibeCheck is surfacing things you act on."
        )

    # Cost predictability
    if summary["last_7_days_analyses"] > 0:
        avg_cost_per_analysis = summary["last_7_days_cost"] / summary["last_7_days_analyses"]
        signals["cost_signal"] = (
            f"Last 7 days: ${summary['last_7_days_cost']:.3f} across "
            f"{summary['last_7_days_analyses']} analyses (~${avg_cost_per_analysis:.4f}/analysis)."
        )

    # Latency
    avg_ms = summary["avg_analyzer_latency_ms"]
    if avg_ms > 60_000:
        signals["latency_warning"] = (
            f"Analyzer averages {avg_ms/1000:.1f}s — slower than expected. May hit lock timeouts."
        )

    return signals


# ─── Helpers ─────────────────────────────────────────────────────────────────

# Pricing per 1M tokens (input). Output is roughly 5x but proportionally small.
COST_PER_1M_INPUT = {
    "haiku": 0.80,
    "sonnet": 3.00,
    "opus": 15.00,
}

COST_PER_1M_OUTPUT = {
    "haiku": 4.00,
    "sonnet": 15.00,
    "opus": 75.00,
}

def compute_cost(input_tokens: int, model: str, output_tokens: Optional[int] = None) -> float:
    """Estimate cost for a single analysis. Output tokens default to 10% of input."""
    if output_tokens is None:
        output_tokens = max(50, input_tokens // 10)
    in_rate = COST_PER_1M_INPUT.get(model, COST_PER_1M_INPUT["haiku"])
    out_rate = COST_PER_1M_OUTPUT.get(model, COST_PER_1M_OUTPUT["haiku"])
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _last_n_day_keys(n: int) -> List[str]:
    today = datetime.now(timezone.utc)
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def _count_active_days(by_day: Dict) -> int:
    return sum(1 for v in by_day.values() if v.get("analyses", 0) > 0 or v.get("tasks", 0) > 0)


def _empty_day() -> Dict:
    return {
        "analyses": 0,
        "static_runs": 0,
        "tasks": 0,
        "tokens": 0,
        "cost": 0.0,
        "findings_created": 0,
        "resolved": 0,
        "dismissed": 0,
        "vg_invocations": 0,
    }
