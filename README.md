# VibeCheck

Build with AI — without second-guessing every decision.

VibeCheck watches your code as you build and tells you what you're getting wrong, what you're overcomplicating, and what's not ready for production. It runs inline, in the same response where Claude makes changes — no waiting, no separate API calls.

**Token cost**: the PostToolUse hook runs a sync regex pass (<200ms, zero tokens), then injects a structured evidence block into Claude's context. Claude confirms findings from that evidence rather than re-reading the file from scratch. Typical overhead is **500–2,000 tokens per response with file changes** (~$0.0003–$0.001 at Haiku rates, ~$0.001–$0.006 at Sonnet rates). Clean responses where nothing is flagged cost closer to 300 tokens. This counts against your existing Claude Code usage.

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

## The questions VibeCheck answers

1. **Am I doing this right?** — catches wrong abstractions, reinvented wheels, approaches that will fight you later
2. **Am I overengineering this?** — flags complexity that exceeds what your current stage needs
3. **Is this safe for production?** — catches auth gaps, SQL injection, hardcoded secrets, missing webhook verification
4. **Am I missing something obvious?** — cross-file consistency, missing migrations, callers not updated
5. **What should I fix before I ship?** — specific `🧪 Before shipping:` line every time, not generic advice
6. **Is the AI coding the way a senior dev would?** — 12 standing engineering rules injected into every project: no false tests, no scope creep, no unsubstantiated performance claims, no half-migrations, no generated files accepted without reading them

## Setup

```bash
npx github:playgroundparth/VibeCheck init
```

That's it. VibeCheck is now active. Restart Claude Code once after running init.

**If you have existing code** (not starting from scratch), also run a one-time scan after init:

```
/vibecheck-scan               # fast (Haiku, ~$0.05) — good for first pass
/vibecheck-scan --deep        # thorough (Sonnet, ~$0.30) — deeper analysis
/vibecheck-scan --model opus  # exhaustive (Opus, ~$2–4) — maximum depth
/vibecheck-scan auth          # focused — weight greps toward an area
```

Going forward, VibeCheck runs automatically after every change — the scan is a one-time catch-up.

## Requirements

- [Claude Code](https://claude.ai/code) installed and authenticated
- Node.js 18+
- Python 3.8+

## How it works

Init writes 12 engineering standards into your project's `CLAUDE.md` — standing rules that apply to every response Claude generates, not just the post-write check. These cover the failure modes that senior devs catch in code review but vibecoders miss: false tests that confirm execution without verifying correctness, scope creep that makes diffs unreviewable, generated migration files accepted without reading them, and unsubstantiated performance claims. The rules are imperative and non-negotiable — not suggestions Claude weighs, but constraints it applies before shipping any change.

The PostToolUse hook runs after every file write. It executes a sync regex pass against the changed file (<200ms, zero tokens), produces a structured evidence block with confidence tiers, and injects that into Claude's context. Claude's job is to confirm each evidence item by reading the cited code — not to detect patterns from scratch. This separation means detection is deterministic (hook-owned) and judgment is LLM-quality (Claude-owned).

Three hooks are installed:

- **PostToolUse hook** — runs sync detection on every file write, injects structured evidence into Claude's context, extracts project facts (auth provider, ORM, webhook setup), launches optional background Semgrep scan on Enhanced/Pro tiers
- **Stop hook** — runs the same static checks as a backstop in case a response ends without a VibeCheck footer (long responses, interrupted tasks). Also logs task completion. In practice the inline check fires reliably because detection happens before Claude generates its response, not after — Claude is reacting to the hook's evidence, not following a CLAUDE.md instruction from memory.
- **SessionStart hook** — injects open findings count and recent context into every new session so nothing is forgotten. Also surfaces any Semgrep/Gitleaks findings from the previous session's background scan.

All findings are stored locally in `.vibecheck/findings.json`. Nothing leaves your machine unless you opt into anonymous usage stats during init.

**Worktree support**: VibeCheck works correctly in git worktrees. All components — hooks, bin scripts, and the scanner — resolve the main repo root via `git rev-parse --git-common-dir` so findings and memory are always shared from the same `.vibecheck/` directory regardless of which worktree you're in.

---

> **⚡ Works significantly better with [Graphify](https://graphify.net/)**
>
> VibeCheck's regex pass finds what's in the file you just changed. Graphify's knowledge graph tells it what calls what, what's exported but never used, and which functions sit on security-critical paths — across the entire codebase. With Graphify, the scanner starts from the graph rather than a grep: it already knows the call chains before reading a single file. Dead exports, architectural hotspots, test coverage gaps — surfaced before VibeCheck even runs its patterns.
>
> Add Graphify to your project, then run `/vibecheck-scan`. The difference is visible.

---

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
| `/vibecheck` | Show open findings summary |
| `/vibecheck vg-001` | Full detail on one finding |
| `/vibecheck-resolve vg-001` | Mark a finding as resolved |
| `/vibecheck-scan` | Scan codebase (Haiku, grep-first, ~$0.05) |
| `/vibecheck-scan --deep` | Deeper scan (Sonnet, ~$0.30) |
| `/vibecheck-scan --model opus` | Exhaustive scan (Opus, ~$2–4) |
| `/vibecheck-scan auth` | Focused scan — weight greps toward an area |
| `/vibecheck-review` | Senior-dev review of everything changed since last commit |
| `/vibecheck-stage mvp\|growth\|prod` | Set project stage to adjust severity thresholds |


## What VibeCheck catches

Two check surfaces with different scope:

**Inline check** — runs after every file change, via hook + Claude confirmation. Covers patterns where a regex can confirm both the risk and the absence of mitigation in the changed file:

| Pattern | Severity | Detection method |
|---------|---------|-----------------|
| Secret / credential hardcoded in source | Critical | Regex, hook-confirmed |
| SQL query built with string concatenation | Critical | Regex, hook-confirmed |
| Shell command built with string concatenation | Critical | Regex, hook-confirmed |
| Unsafe deserialization (`pickle.loads`, `yaml.load`) | Critical | Regex, hook-confirmed |
| Open redirect: `res.redirect(req.query.*)` | Critical | Regex, hook-confirmed |
| Webhook endpoint with no signature verification | Critical | File-scope check, Claude-confirmed |
| Env var used in code but absent from `.env.example` | Critical | Cross-file check, hook-confirmed |
| `.env` file committed | Critical | Filename check |
| `.env` not in `.gitignore` | Critical | File check |
| New source file with no callers | Pitfall | Reverse-dep map |
| Schema changed, no migration file | Critical | Claude-confirmed |
| AUTH-01: route touches user data, no auth check | Critical | Claude-confirmed |
| AUTH-08: exported function signature changed, callers not updated | Critical | Claude-confirmed |
| Cross-file inconsistency (added to collection, cleanup not updated) | Pitfall | Claude-confirmed |

**`/vibecheck-review`** — on-demand, runs after larger changes or before shipping. Applies the full 30-pattern catalog to everything changed since the last commit:

| Category | Patterns |
|---------|---------|
| **Auth** (AUTH 01–08) | Route auth, webhook sig, service-role exposure, auth ordering, localStorage tokens, custom JWT, CORS wildcard, sensitive field leakage |
| **Data** (DATA 01–08) | In-memory counters, missing migrations, unguarded awaits, payment idempotency, N+1 queries, read-then-write races, derived data, serverless pooling |
| **Architecture** (ARCH 01–08) | Single-use service wrappers, premature caching, custom email/queue, wrong-layer logic, dead exports, signature drift |
| **Operations** (OPS 01–06) | Undocumented env vars, debug flags in prod config, missing retries, missing ErrorBoundary, no health check, AI route timeout on Vercel |
| **Testing** (TEST-01) | Mutation testing not configured — tests exist but aren't verified to catch real bugs |

Two OPS patterns (undocumented env vars, dead exports) run automatically on every change via the hook — they don't wait for `/vibecheck-review`.

**TEST-01 is `will-bite-you`, not `nice-to-have`**: Claude writes both the implementation and the tests. AI-generated tests routinely assert that code runs without error, not that it produces correct results. Mutation testing (Stryker for JS/TS, mutmut for Python, Pitest for Java) is the only reliable way to verify your tests would catch a real bug — VibeCheck surfaces it when tests exist but no mutation config is found.

**Never reported**: code style, naming, console.log (unless leaking a secret), large files, anything already in existing open findings.

## Integration skills

When VibeCheck detects that you're using Stripe, Supabase, Clerk, Prisma, OpenAI, or Vercel, it auto-installs an integration skill into `.claude/skills/`. These are focused guidance documents — they don't replace the anti-pattern catalog, they add integration-specific rules on top of it (webhook verification patterns, connection pooling specifics, RLS gotchas, etc.).

`/vibecheck-review` automatically reads the relevant skill when the changed files match the integration.

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
- Usage telemetry is **currently not collected** — the opt-in dialog is placeholder until a PostHog project is configured. No data is sent regardless of your answer during `init`.
- When telemetry is enabled in a future release: only event names and counts will be sent (never file paths, code, or finding content), via PostHog. You'll be able to opt out with `VIBECHECK_TELEMETRY=0` or `DO_NOT_TRACK=1`.

## Development

```bash
npm test                        # runs the Python test suite (33 assertions)
python3 tests/test_project_map.py  # same, directly
```

`tests/golden/` contains the behavioral spec for the LLM review layer — 9 annotated scenarios covering the full verdict range, with expected findings, evidence anchoring requirements, and explicit anti-patterns. Read these before changing `CLAUDE.template.md`.

## License

MIT
