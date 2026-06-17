# VibeCheck

Build with AI — without second-guessing every decision.

VibeCheck watches your code as you build and tells you what you're getting wrong, what you're overcomplicating, and what's not ready for production. It runs inline, in the same response where the AI makes changes — no waiting, no separate API calls.

Works with **Claude Code**, **Google Antigravity**, and **OpenAI Codex** — CLI and macOS Desktop apps.

**Token cost**: the PostToolUse hook runs a sync regex pass (<200ms, zero tokens), then injects a structured evidence block into the AI's context. The AI confirms findings from that evidence rather than re-reading the file from scratch. Typical overhead is **500–2,000 tokens per response with file changes** (~$0.0003–$0.001 at Haiku/Flash rates, ~$0.001–$0.006 at Sonnet/Pro rates). Clean responses where nothing is flagged cost closer to 300 tokens. This counts against your existing AI usage.

## What it looks like

**Before writing code**, the AI walks a decision ladder and states which rung stopped it:

```
Rung 2 — fetch is native since Node 18. No package needed.

[proceeds to write code using fetch]
```

Or for a common problem category:

```
Rung 2 — zod is already installed in this project.
I'll use it for the schema instead of writing a custom validator.
```

**After the AI finishes a task**, at the bottom of the same response:

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
🛡️  VibeCheck: Active (full mode)
🤖 Model: Claude Sonnet (auto-selected)

⚡ vc-001 — Command files added but uninstall list not updated
   Why: uninstall.js will leave vibecheck-help.md behind after removal
   Fix → paste into Claude:
   "In uninstall.js, add vibecheck-help.md to the commandFiles array on line 167."
```

## The questions VibeCheck answers

1. **Am I doing this right?** — catches wrong abstractions, reinvented wheels, approaches that will fight you later
2. **Am I overengineering this?** — flags complexity that exceeds what your current stage needs
3. **Is this safe for production?** — catches auth gaps, SQL injection, hardcoded secrets, missing webhook verification
4. **Am I missing something obvious?** — cross-file consistency, missing migrations, callers not updated
5. **What should I fix before I ship?** — specific `🧪 Before shipping:` line every time, not generic advice
6. **Is the AI coding the way a senior dev would?** — a mandatory pre-implementation decision ladder forces the AI to check for native APIs, stdlib, installed packages, and well-known ecosystem solutions *before* writing a single line

## Setup

```bash
npx github:playgroundparth/VibeCheck init
```

That's it. VibeCheck installs into whichever AI coding apps are active in your project (Claude Code, Antigravity, Codex — or all three). Restart the app once after running init.

**If you have existing code** (not starting from scratch), also run a one-time scan after init:

```
/vibecheck-scan               # fast (lite mode) — good for first pass
/vibecheck-scan --deep        # thorough (full mode) — deeper analysis
/vibecheck-scan --pro         # exhaustive (pro mode) — maximum depth
/vibecheck-scan auth          # focused — weight greps toward an area
```

Going forward, VibeCheck runs automatically after every change — the scan is a one-time catch-up.

## Requirements

- One or more of: [Claude Code](https://claude.ai/code), [Google Antigravity](https://deepmind.google/antigravity), [OpenAI Codex](https://openai.com/codex)
- Node.js 18+
- Python 3.8+

## How it works

**Before writing or planning anything**, the AI runs a 4-rung decision ladder injected at the top of the system prompt. It fires on every implementation request — before the AI formulates an approach, proposes a plan, or writes a single line:

1. **Does this need to exist?** — YAGNI. If the user didn't ask for it, skip it.
2. **Does a trusted existing solution do this?** — The AI checks (in order): native platform APIs, stdlib, installed packages, and established ecosystem tools. A senior dev already knows that `crypto.randomUUID()` replaced the `uuid` package, that `fetch` is native since Node 18, that `structuredClone()` replaced `_.cloneDeep`, that `[...new Set(arr)]` is one line. It also knows the industry-standard answer for common problem categories: zod for validation, Resend for email, BullMQ for queues, next-auth for auth. The AI must state which rung stopped the search out loud, before any code or plan appears.
3. **Is it one line?** — Write one line.
4. **Write the minimum that works** — covering trust boundaries, data safety, security, and accessibility. Nothing else.

The output is visible in every response. You'll see the rung called out before the code block.

**After every file write**, the PostToolUse hook runs a sync regex pass (<200ms, zero tokens), produces a structured evidence block with confidence tiers, and injects that into the AI's context. The AI confirms each evidence item by reading the cited code — detection is deterministic (hook-owned), judgment is LLM-quality (AI-owned).

**Static checks** also run on changed files after every write (zero tokens, <100ms). These catch patterns that don't need LLM judgment:

- Native API replacements: `uuid` → `crypto.randomUUID()`, `node-fetch` → `fetch`, `_.cloneDeep` / `JSON.parse(JSON.stringify(...))` → `structuredClone()`, `Math.random()` for IDs → `crypto.randomUUID()`
- Installed dep ignored: date-fns installed but custom date formatter written, zod installed but custom validator written, p-retry installed but custom retry loop written, lodash installed but debounce reimplemented
- Secrets hardcoded, `.env` committed, `.env` not in `.gitignore`, missing lock file, missing README

**Architecture checks** (offline, <500ms, zero tokens):
- **ARCH-CYCLE**: circular dependency cycles (Tarjan SCC) — e.g. A → B → C → A
- **ARCH-GOD**: god-file outliers (large file size + high fan-in)
- **ARCH-LAYER**: architectural layer violations (e.g. `infra/` module importing from `api/`)
- **ARCH-DUP**: code duplication detector using a sliding-window hash
- **ARCH-DEAD**: dead/unreachable files (zero importers, excluding entry points and configs)
- **ARCH-DRIFT**: architectural coupling drift (module gained >5 new importers since last scan)

**12 engineering standards** are written into `CLAUDE.md` — standing rules that apply to every response: no false tests, no scope creep, no unsubstantiated performance claims, no half-migrations, no generated files accepted without reading them.

Three hooks are installed per app:

- **PostToolUse hook** — runs sync detection on every file write, injects structured evidence into the AI's context, extracts project facts (auth provider, ORM, webhook setup), launches optional background Semgrep scan on Enhanced/Pro tiers
- **Stop hook** — runs the same static checks as a backstop in case a response ends without a VibeCheck footer (long responses, interrupted tasks). Also logs task completion.
- **SessionStart hook** — injects open findings count and recent context into every new session so nothing is forgotten. Also surfaces any Semgrep/Gitleaks findings from the previous session's background scan.

Hooks are installed into each active app's workspace directory (`.claude/`, `.agents/`, `.codex/`) and registered globally in the app's user-level settings file — so they fire in git worktrees and macOS Desktop apps without any extra configuration.

All findings are stored locally in `.vibecheck/findings.json`. Nothing leaves your machine unless you opt into anonymous usage stats during init.

**Worktree support**: VibeCheck works correctly in git worktrees. All components — hooks, bin scripts, and the scanner — resolve the main repo root via `git rev-parse --git-common-dir` so findings and memory are always shared from the same `.vibecheck/` directory regardless of which worktree you're in.

---

> **⚡ Works significantly better with [Graphify](https://graphify.net/)**
>
> VibeCheck's regex pass finds what's in the file you just changed. Graphify's knowledge graph tells it what calls what, what's exported but never used, and which functions sit on security-critical paths — across the entire codebase. With Graphify, the scanner starts from the graph rather than a grep: it already knows the call chains before reading a single file. Dead exports, architectural hotspots, test coverage gaps — surfaced before VibeCheck even runs its patterns.
>
> Add Graphify to your project, then run `/vibecheck-scan`. The difference is visible.

---

## Modes

VibeCheck has four intensity modes. Switch with `/vibecheck <mode>` — the model is auto-selected for your platform:

| Mode | What runs | Claude | Antigravity | Codex |
|---|---|---|---|---|
| `lite` | Regex only, no async | Haiku | Gemini Flash | GPT-5.4 Mini |
| `full` *(default)* | Regex + Semgrep | Sonnet | Gemini Pro | GPT-5.4 |
| `pro` | Regex + Semgrep + Gitleaks + mutation | Opus | Gemini Pro | GPT-5.5 |
| `off` | Hooks installed but silent | — | — | — |

You never need to pick a model manually. Switching mode is all you need.

## Verdicts

Every VibeCheck footer ends with one of three verdicts:

| Verdict | Meaning |
|---------|---------|
| `✅ Safe to continue` | No blocking issues — keep building |
| `⚠️ OK for MVP, not prod` | Architectural concern, overbuilding, or cross-file gap — fine for now, fix before real users |
| `❌ Fix before shipping` | Security vulnerability or correctness bug — stop and fix this |

The verdict is a holistic judgment, not a mechanical count.

## Commands

| Command | Subcommands / Options | What it does |
|---|---|---|
| **/vibecheck** | | **The Central Dashboard.** Lists open findings, mode, and auto-selected model. |
| | `<id>` | View details for finding `<id>` (e.g. `/vibecheck vc-003`). |
| | `resolve <id> [note]` | Mark finding `<id>` as resolved. |
| | `report` | Regenerate the HTML dashboard and open it in the side panel. |
| | `timeline` | Print the append-only event log (decisions, changes, milestones). |
| | `lite \| full \| pro \| off` | Set checking intensity mode. Auto-selects the platform model. |
| | `stage mvp \| growth \| prod` | Set project stage to adjust severity thresholds. |
| | `help` | Print quick reference. |
| **/vibecheck-scan** | | **Full Repository Scan.** Runs AST-first analysis across the codebase. |
| | `--deep` \| `--pro` | Deeper scan tiers (Semgrep / Semgrep+Gitleaks). |
| | `[area]` | Focus scan on a path or keyword (e.g. `auth`, `src/payments`). |
| **/vibecheck-review** | | **Diff Review.** Analyze the current git diff for security and correctness. |
| **/vibecheck-skills** | | **Integration Skill Manager.** List auto-proposed context skills. |
| | `promote <name>` | Activate a proposed skill into the active skills directory. |
| **/vibecheck-help** | | Display the VibeCheck quick reference. |

## What VibeCheck catches

Three check surfaces, each with a different scope:

**Pre-implementation ladder** — fires at response start, before any planning or writing. The AI states out loud which rung stopped it. Catches: reinvented native APIs, installed deps ignored, custom solutions for problems the ecosystem already answers, unnecessary features.

**Inline check** — runs after every file change, via hook + AI confirmation:

| Pattern | Severity | Detection method |
|---------|---------|-----------------|
| Secret / credential hardcoded in source | Critical | Regex, hook-confirmed |
| SQL query built with string concatenation | Critical | Regex, hook-confirmed |
| Shell command built with string concatenation | Critical | Regex, hook-confirmed |
| Unsafe deserialization (`pickle.loads`, `yaml.load`) | Critical | Regex, hook-confirmed |
| Open redirect: `res.redirect(req.query.*)` | Critical | Regex, hook-confirmed |
| Webhook endpoint with no signature verification | Critical | File-scope check, AI-confirmed |
| Env var used in code but absent from `.env.example` | Critical | Cross-file check, hook-confirmed |
| `.env` file committed | Critical | Filename check |
| `.env` not in `.gitignore` | Critical | File check |
| New source file with no callers | Pitfall | Reverse-dep map |
| Schema changed, no migration file | Critical | AI-confirmed |
| AUTH-01: route touches user data, no auth check | Critical | AI-confirmed |
| AUTH-08: exported function signature changed, callers not updated | Critical | AI-confirmed |
| Cross-file inconsistency (added to collection, cleanup not updated) | Pitfall | AI-confirmed |
| `uuid` package → `crypto.randomUUID()` is native | Hygiene | Static check |
| `node-fetch` → `fetch` is native since Node 18 | Hygiene | Static check |
| `_.cloneDeep` / `JSON.parse(JSON.stringify(...))` → `structuredClone()` | Hygiene | Static check |
| `Math.random()` for IDs/tokens → `crypto.randomUUID()` | Hygiene | Static check |
| External base64 package → `Buffer.from()` is native | Hygiene | Static check |
| URL string concatenation → `new URL()` + `URLSearchParams` | Hygiene | Static check |
| Custom dedup function → `[...new Set(arr)]` | Hygiene | Static check |
| Custom date formatter when date-fns/dayjs is installed | Hygiene | Static check |
| Custom validator when zod/joi/yup is installed | Hygiene | Static check |
| Custom retry loop when p-retry is installed | Hygiene | Static check |
| Custom HTTP wrapper when axios/got is installed | Hygiene | Static check |
| Custom utility function when lodash is installed | Hygiene | Static check |

**`/vibecheck-review`** — on-demand, runs after larger changes or before shipping. Applies the full 30-pattern catalog to everything changed since the last commit:

| Category | Patterns |
|---------|---------|
| **Auth** (AUTH 01–08) | Route auth, webhook sig, service-role exposure, auth ordering, localStorage tokens, custom JWT, CORS wildcard, sensitive field leakage |
| **Data** (DATA 01–08) | In-memory counters, missing migrations, unguarded awaits, payment idempotency, N+1 queries, read-then-write races, derived data, serverless pooling |
| **Architecture** (ARCH 01–08) | Single-use service wrappers, premature caching, custom email/queue, wrong-layer logic, dead exports, signature drift |
| **Operations** (OPS 01–06) | Undocumented env vars, debug flags in prod config, missing retries, missing ErrorBoundary, no health check, AI route timeout on Vercel |
| **Testing** (TEST-01) | Mutation testing not configured — tests exist but aren't verified to catch real bugs |

Two OPS patterns (undocumented env vars, dead exports) run automatically on every change via the hook — they don't wait for `/vibecheck-review`.

**TEST-01 is `will-bite-you`, not `nice-to-have`**: AI coding tools write both the implementation and the tests. AI-generated tests routinely assert that code runs without error, not that it produces correct results. Mutation testing (Stryker for JS/TS, mutmut for Python, Pitest for Java) is the only reliable way to verify your tests would catch a real bug — VibeCheck surfaces it when tests exist but no mutation config is found.

**Never reported**: code style, naming, console.log (unless leaking a secret), large files, anything already in existing open findings.

## Integration skills

When VibeCheck detects that you're using Stripe, Supabase, Clerk, Prisma, OpenAI, or Vercel, it auto-installs an integration skill into your active app's skills directory. These are focused guidance documents — they don't replace the anti-pattern catalog, they add integration-specific rules on top of it (webhook verification patterns, connection pooling specifics, RLS gotchas, etc.).

`/vibecheck-review` automatically reads the relevant skill when the changed files match the integration.

Use `/vibecheck-skills` to see what's been proposed, and `/vibecheck-skills promote <name>` to activate one.

## Updating

When a new version is released, run this in your project to pull in the latest hooks, lib, and commands:

```bash
npx github:playgroundparth/VibeCheck update
```

This re-copies the updated VibeCheck files into all active workspace directories (`.claude/`, `.agents/`, `.codex/`) — your `.vibecheck/` findings, `CLAUDE.md`, and global settings are never touched. Restart the app after updating.

## Uninstall

```bash
npx github:playgroundparth/VibeCheck uninstall          # full removal
npx github:playgroundparth/VibeCheck uninstall --keep-data   # remove hooks, keep findings history
```

Removes hooks from all active workspace directories and deregisters them from each app's global settings file.

## Checking your installation

```bash
npx github:playgroundparth/VibeCheck doctor
```

Reports pass/warn/fail for every component across all installed apps: hook files, lib files, commands, global settings registration, CLAUDE.md section, Python availability.

## Privacy

- All findings are stored locally in `.vibecheck/` (auto-added to `.gitignore`)
- Usage telemetry is **currently not collected** — the opt-in dialog is placeholder until a PostHog project is configured. No data is sent regardless of your answer during `init`.
- When telemetry is enabled in a future release: only event names and counts will be sent (never file paths, code, or finding content), via PostHog. You'll be able to opt out with `VIBECHECK_TELEMETRY=0` or `DO_NOT_TRACK=1`.

## Debugging

```bash
export VIBECHECK_DEBUG=1
```

Writes a debug log to `.vibecheck/debug.log` while hooks are running. Useful for diagnosing why a hook isn't firing or why a finding isn't appearing.

## Development

```bash
npm test                        # runs the Python test suite (33 assertions)
python3 tests/test_project_map.py  # same, directly
```

`tests/golden/` contains the behavioral spec for the LLM review layer — 9 annotated scenarios covering the full verdict range, with expected findings, evidence anchoring requirements, and explicit anti-patterns. Read these before changing `CLAUDE.template.md`.

## License

MIT
