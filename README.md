# VibeCheck

Build with AI — without second-guessing every decision.

VibeCheck watches your code as you build and tells you what you're getting wrong, what you're overcomplicating, and what's not ready for production. It runs inline, in the same response where Claude makes changes — no waiting, no extra cost.

## What it looks like

After Claude finishes a task, at the bottom of the same response:

```
---
VibeCheck: ⚠️ OK for MVP, not prod  · ⚡ 1 pitfall
🧪 Before shipping: test that uninstall removes all command files, not just the original set
💡 You added to a collection in 3 places but the cleanup list only has the original 5.
```

Or when there's a real problem:

```
---
VibeCheck: ❌ Fix before shipping  · 🔴 1 critical
🧪 Before shipping: test the webhook endpoint with a forged signature — it should reject it
```

Or when it's clean:

```
---
VibeCheck: ✅ Safe to continue
🧪 Before shipping: confirm the new route returns 401 for unauthenticated requests
```

Type `/vibecheck`:

```
⚡ vg-001 — Command files added but uninstall list not updated
   Why: uninstall.js will leave vibecheck-skills.md and 2 others behind after removal
   Fix → paste into Claude:
   "In uninstall.js, add vibecheck-skills.md, vibecheck-promote-skill.md, and
    vibecheck-model.md to the commandFiles array on line 105."
```

## The five questions VibeCheck answers

1. **Am I doing this right?** — catches wrong abstractions, reinvented wheels, approaches that will fight you later
2. **Am I overengineering this?** — flags complexity that exceeds what your current stage needs
3. **Is this safe for production?** — catches auth gaps, SQL injection, hardcoded secrets, missing webhook verification
4. **Am I missing something obvious?** — cross-file consistency, missing migrations, callers not updated
5. **What should I fix before I ship?** — specific `🧪 Before shipping:` line every time, not generic advice

## Setup

```bash
npx github:playgroundparth/VibeCheck init
```

That's it. VibeCheck is now active. Restart Claude Code once after running init.

**If you have existing code** (not starting from scratch), also run this after init to scan your history for risks:

```bash
npx github:playgroundparth/VibeCheck scan
```

Or type `/vibecheck-scan` inside Claude Code. Going forward, VibeCheck runs automatically after every change — the scan is a one-time catch-up.

## Requirements

- [Claude Code](https://claude.ai/code) installed and authenticated
- Node.js 18+
- Python 3.8+

## How it works

VibeCheck adds a section to your `CLAUDE.md` that tells Claude to run a judgment pass at the end of every response where files were changed. Claude reads the files it just modified — and up to 2 related "maintenance files" (cleanup scripts, install lists, caller files) — then gives you a verdict, a specific test to run, and any findings worth tracking.

It also installs three hooks:

- **Stop hook** — logs task completion, runs fast static checks (hardcoded secrets, auth bypass patterns), sends a fallback reminder if Claude missed the inline check
- **SessionStart hook** — injects open findings count and recent context into every new session so nothing is forgotten
- **PostToolUse hook** — silently extracts project facts (auth provider, ORM, webhook setup) from files as they're read or written

All findings are stored locally in `.vibecheck/findings.json`. Nothing leaves your machine unless you opt into anonymous usage stats during init.

## Verdicts

Every VibeCheck footer ends with one of three verdicts:

| Verdict | Meaning |
|---------|---------|
| `✅ Safe to continue` | No blocking issues — keep building |
| `⚠️ OK for MVP, not prod` | Architectural concern, overbuilding, or cross-file gap — fine for now, fix before real users |
| `❌ Fix before shipping` | Security vulnerability or correctness bug — stop and fix this |

The verdict is a holistic judgment, not a mechanical count.

## Commands

| Command | What it does |
|---|---|
| `/vibecheck` | Show open findings with fix prompts |
| `/vibecheck-detail vg-001` | Full detail on one finding |
| `/vibecheck-resolve vg-001` | Mark as resolved |
| `/vibecheck-scan` | Run a one-time scan of your codebase |
| `/vibecheck-status` | Health metrics — findings, resolution rate, cost |
| `/vibecheck-timeline` | Activity log — what changed and when |
| `/vibecheck-report` | Generate a full HTML health dashboard |
| `/vibecheck-skills` | Review proposed skills |
| `/vibecheck-promote-skill` | Promote a proposed skill to active |
| `/vibecheck-model haiku\|sonnet` | Switch analyzer model |
| `/vibecheck-doctor` | Check installation health |

## Health report

`/vibecheck-report` generates `.vibecheck/health-report.html` — a full dashboard you can open in a browser:

- All open findings grouped by severity, with effort/impact tags
- Quick wins (high impact, low effort) called out separately
- Resolved findings history
- Activity timeline (what changed and when)
- Learned patterns VibeCheck has built for your project

## Works better with these tools

VibeCheck detects these automatically during `init` and uses them if present — no extra setup needed:

**[OpenSpec](https://github.com/Fission-AI/OpenSpec)** — if you have OpenSpec active, VibeCheck cross-references your API specs when analyzing routes. It can flag when a new endpoint isn't in the spec, or when implementation diverges from the declared contract.

**[ICM](https://github.com/rtk-ai/icm)** — if you have ICM (Intelligent Context Memory) installed, VibeCheck uses it as a richer memory store for project context. Without ICM, VibeCheck falls back to its own `.vibecheck/context_log.jsonl`.

**[Graphify](https://graphify.net/)** — if you have a Graphify code graph, VibeCheck uses it to understand blast radius when files change (which other files are affected), improving which files it chooses to analyze.

## What VibeCheck catches

**Critical** — flags only when there's a concrete exploit or definite breakage:
- Route handles user data without an auth check
- User input in a database query (SQL injection)
- User-controlled path in file read/write (path traversal)
- Webhook/payment endpoint without signature verification
- API response leaks data the caller shouldn't see
- Secret or credential hardcoded in source
- Logic that will definitely crash or corrupt data in production

**Pitfall** — architectural and decision traps, not immediately exploitable:
- OVERBUILDING — complexity that exceeds what this stage of the project needs
- REINVENTING — building something that already exists and works better (custom JWT, custom email, custom queues)
- WRONG ABSTRACTION — structure that will resist the next obvious change
- Cross-file inconsistency — added to a collection but forgot to update cleanup/install lists
- In-memory state that won't survive restarts
- New feature built on top of broken code

**Hygiene**:
- Non-trivial feature with no test file
- `await` without try/catch in payment, auth, or DB paths

**Good to have** — minor only:
- Missing rate limiting on public endpoints
- Missing input validation on user-facing forms

**Never reported**: code style, naming, console.log, large files, anything already in existing findings.

## Updating

When a new version is released, run this in your project to pull in the latest hooks, lib, and commands:

```bash
npx github:playgroundparth/VibeCheck update
```

This re-copies only the VibeCheck files into `.claude/` — your `.vibecheck/` findings, `CLAUDE.md`, and `settings.json` are never touched. Restart Claude Code after updating.

## Uninstall

```bash
npx github:playgroundparth/VibeCheck uninstall          # full removal
npx github:playgroundparth/VibeCheck uninstall --keep-data   # remove hooks, keep findings history
```

## Checking your installation

```bash
npx github:playgroundparth/VibeCheck doctor
```

Reports pass/warn/fail for every component: hook files, lib files, commands, global settings registration, CLAUDE.md section, Python availability.

## Privacy

- All findings are stored locally in `.vibecheck/` (auto-added to `.gitignore`)
- Anonymous usage stats are **off by default** — you're asked during `init`
- If opted in: only event names and counts are sent, never file paths, code, or finding content
- Opt out anytime: `VIBECHECK_TELEMETRY=0` or `DO_NOT_TRACK=1`

## License

MIT
