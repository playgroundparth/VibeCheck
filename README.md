# VibeCheck

A security analysis agent for vibe coders using Claude Code. Watches what you build, flags real risks in plain English, and gives you paste-ready fixes — all inline, same response, no waiting.

## What it looks like

After Claude finishes a task, at the bottom of the same response:

```
---
VibeCheck: 🔴 1 critical · ⚡ 1 pitfall
💡 No tests here — if this breaks in prod, you'll be debugging blind.
```

Type `/vibecheck`:

```
🔴 vg-001 — Anyone can access /dashboard without logging in
   Why: users can see each other's data without authenticating
   Fix → paste into Claude:
   "Add an auth check at the top of the dashboard route. Use the same
    pattern already in src/middleware/auth.ts — requireAuth() before
    any data is returned."
```

## Setup

```bash
npx github:playgroundparth/VibeCheck init
```

That's it. VibeCheck is now active. Restart Claude Code once after running init.

**For existing codebases:**

```bash
npx github:playgroundparth/VibeCheck scan
```

## Requirements

- [Claude Code](https://claude.ai/code) installed and authenticated
- Node.js 18+
- Python 3.8+

## How it works

VibeCheck adds a section to your `CLAUDE.md` that tells Claude to run security analysis at the end of every response where files were changed. No subprocess, no background agent, no waiting — Claude reads the files it just wrote and checks them inline.

It also installs three hooks:

- **Stop hook** — logs task completion, runs fast static checks (hardcoded secrets, auth bypass patterns), sends a fallback reminder if Claude missed the inline check
- **SessionStart hook** — injects open findings count and recent context into every new session so nothing is forgotten
- **PostToolUse hook** — silently extracts project facts (auth provider, ORM, webhook setup) from files as they're read or written

All findings are stored locally in `.vibeguard/findings.json`. Nothing leaves your machine unless you opt into anonymous usage stats during init.

## Commands

| Command | What it does |
|---|---|
| `/vibecheck` | Show open findings with fix prompts |
| `/vibecheck-detail vg-001` | Full detail on one finding |
| `/vibecheck-resolve vg-001` | Mark as resolved |
| `/vibecheck-scan` | Run a one-time scan of your codebase |
| `/vibecheck-status` | Health metrics — findings, resolution rate, cost |
| `/vibecheck-report` | Generate a full HTML health dashboard |

## Health report

`/vibecheck-report` generates `.vibeguard/health-report.html` — a full dashboard you can open in a browser:

- All open findings grouped by severity, with effort/impact tags
- Quick wins (high impact, low effort) called out separately
- Resolved findings history
- Activity timeline (what changed and when)
- Learned patterns VibeCheck has built for your project

## Works better with these tools

VibeCheck detects these automatically during `init` and uses them if present — no extra setup needed:

**[OpenSpec](https://github.com/Fission-AI/OpenSpec)** — if you have OpenSpec active, VibeCheck cross-references your API specs when analyzing routes. It can flag when a new endpoint isn't in the spec, or when implementation diverges from the declared contract.

**[ICM](https://github.com/rtk-ai/icm)** — if you have ICM (Intelligent Context Memory) installed, VibeCheck uses it as a richer memory store for project context. Without ICM, VibeCheck falls back to its own `.vibeguard/context_log.jsonl`.

**[Graphify](https://graphify.net/)** — if you have a Graphify code graph, VibeCheck uses it to understand blast radius when files change (which other files are affected), improving which files it chooses to analyze.

## What VibeCheck catches

**Critical** — flags only when there's a concrete exploit:
- Route handles user data without an auth check
- User input in a database query (SQL injection)
- User-controlled path in file read/write (path traversal)
- Webhook/payment endpoint without signature verification
- API response leaks data the caller shouldn't see
- Secret or credential hardcoded in source

**Pitfall** — architectural traps, not immediately exploitable:
- In-memory rate limiting or counters (won't survive restarts)
- Custom auth/JWT instead of using a library
- New feature built on top of code that is already broken

**Hygiene**:
- Non-trivial feature with no test file
- `await` without try/catch in payment, auth, or DB paths

**Good to have** — minor only:
- Missing rate limiting on public endpoints
- Missing input validation on user-facing forms

**Never reported**: code style, naming, console.log, large files, anything already in existing findings.

## Context capture

VibeCheck also tells Claude to capture important context before responding — architecture decisions, errors resolved, user preferences. This is stored in `.vibeguard/context_log.jsonl` and injected into every new session so Claude remembers what matters across conversations.

## Cost

VibeCheck's inline analysis runs inside the same Claude session — no extra API calls, no extra cost. The only optional cost is the static check subprocess (Python, runs in <100ms).

## Uninstall

```bash
npx github:playgroundparth/VibeCheck uninstall          # full removal
npx github:playgroundparth/VibeCheck uninstall --keep-data   # remove hooks, keep findings history
```

## Privacy

- All findings are stored locally in `.vibeguard/` (auto-added to `.gitignore`)
- Anonymous usage stats are **off by default** — you're asked during `init`
- If opted in: only event names and counts are sent, never file paths, code, or finding content
- Opt out anytime: `VIBECHECK_TELEMETRY=0` or `DO_NOT_TRACK=1`

## License

MIT
