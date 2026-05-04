#!/usr/bin/env python3
"""
VibeCheck telemetry — anonymous usage events, opt-out by default.

What is sent:
  - event name (e.g. "task_completed", "finding_added")
  - severity (for finding events only)
  - VibeCheck version
  - anonymous machine UUID (generated once, stored in ~/.vibecheck/id)

What is never sent:
  - file paths, file contents, finding titles, project names
  - IP address ($ip: null)
  - any PII

Opt out: set VIBECHECK_TELEMETRY=0 or DO_NOT_TRACK=1.
Automatically disabled in CI.
"""

import json
import os
import threading
import uuid
from pathlib import Path

# Replace with your PostHog project API key.
# Safe to embed publicly — write-only, cannot read data.
POSTHOG_KEY = "REPLACE_WITH_POSTHOG_PROJECT_KEY"
POSTHOG_HOST = "https://us.i.posthog.com"  # or your reverse proxy

VERSION = "0.1.0"
_ID_FILE = Path.home() / ".vibecheck" / "id"


def _is_enabled(config: dict) -> bool:
    """Check if telemetry is allowed. Off unless user opted in during init."""
    if os.environ.get("VIBECHECK_TELEMETRY") == "0":
        return False
    if os.environ.get("DO_NOT_TRACK") == "1":
        return False
    if os.environ.get("CI") or os.environ.get("CONTINUOUS_INTEGRATION"):
        return False
    return config.get("telemetry", False)


def _machine_id() -> str:
    """Get or create a stable anonymous machine UUID."""
    try:
        _ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _ID_FILE.exists():
            return _ID_FILE.read_text().strip()
        uid = str(uuid.uuid4())
        _ID_FILE.write_text(uid)
        return uid
    except Exception:
        return "unknown"


def _fire(event: str, properties: dict, config: dict) -> None:
    """Send event to PostHog in a background thread. Never blocks, never raises."""
    if not _is_enabled(config):
        return
    if POSTHOG_KEY == "REPLACE_WITH_POSTHOG_PROJECT_KEY":
        return  # not configured yet

    def _send():
        try:
            import urllib.request
            payload = json.dumps({
                "api_key": POSTHOG_KEY,
                "event": event,
                "distinct_id": _machine_id(),
                "properties": {
                    **properties,
                    "$ip": None,  # disable IP tracking
                    "vibecheck_version": VERSION,
                },
            }).encode()
            req = urllib.request.Request(
                f"{POSTHOG_HOST}/capture/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass  # never crash the hook

    threading.Thread(target=_send, daemon=True).start()


# ── Public API ────────────────────────────────────────────────────────────────

def track_init(config: dict) -> None:
    _fire("vibecheck_init", {
        "has_integrations": bool(config.get("integrations")),
        "global_registry": config.get("global_registry", False),
    }, config)


def track_task_completed(config: dict) -> None:
    _fire("task_completed", {}, config)


def track_finding_added(config: dict, severity: str) -> None:
    _fire("finding_added", {"severity": severity}, config)


def track_vibecheck_invoked(config: dict) -> None:
    _fire("vibecheck_invoked", {}, config)


def track_finding_resolved(config: dict, was_dismissed: bool = False) -> None:
    _fire("finding_resolved", {"dismissed": was_dismissed}, config)


def load_config(cwd: Path) -> dict:
    """Load .vibeguard/config.json. Returns empty dict on failure."""
    try:
        cfg_path = cwd / ".vibeguard" / "config.json"
        if cfg_path.exists():
            return json.loads(cfg_path.read_text())
    except Exception:
        pass
    return {}
