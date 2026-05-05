# Project

## Context Capture — MANDATORY triggers

You MUST append to `.vibecheck/context_log.jsonl` BEFORE responding when ANY of these happen:

1. **Error resolved** — you fixed a bug or unblocked something that was failing
2. **Architecture/design decision** — a non-obvious choice was made (why matters, not just what)
3. **User preference discovered** — user corrected your approach, style, or rejected something
4. **Significant task completed** — multi-step feature or refactor finished
5. **20+ tool calls without a store** — write a progress summary

Do this BEFORE the rest of your response. Not after. Not "I'll note that." Write it now.

Do NOT store: trivial details, build logs, git status, anything already in CLAUDE.md.

### Format — append one line to `.vibecheck/context_log.jsonl`:
```json
{"ts":"ISO-timestamp","type":"error-resolved|decision|preference|task-completed|progress","summary":"what happened and why it matters","importance":"high|critical"}
```

To append: Read the file first (or treat as empty if missing), then Write the full content with the new line added.

---

## VibeCheck (active) — continuous judgment layer

After ANY response where you used Write, Edit, or MultiEdit tools, run this at the END of your response. The goal is not "what do I see wrong in this file?" — it is "given everything I know about this project, what must be true for this change to be safe?"

---

### Step 1 — Load context

Read these files (treat as `{}` / `[]` if missing):

- `.vibecheck/memory.json` — project identity, known conventions, recent misses
- `.vibecheck/timeline.json` — last 10 events
- `.vibecheck/findings.json` — existing findings + next ID
- `.vibecheck/project_map.json` — artifact groups (lifecycle relationships between files)
- `.vibecheck/context_log.jsonl` — last 5 notes from prior sessions

---

### Step 2 — Build a review brief (internal reasoning, not written out)

Based on what you read in Step 1 and what files you just changed:

1. **Classify changed files** against `project_map.artifact_groups`:
   - Does any changed file match a `source_glob` in the artifact groups?
   - If yes: note the group name and its lifecycle files (`installed_by`, `updated_by`, `removed_by`, `documented_in`, etc.)

2. **Check timeline** for recent findings in the same area:
   - If a similar finding was added recently → inspect the relevant lifecycle files more aggressively

3. **Check memory**:
   - `known_conventions` — what patterns has this project established that must hold?
   - `recent_misses` — what has slipped through before that you should look for again?

4. **Check docs**: does the change match what README or docs promise users?

This brief is your working set for Steps 3–5. It tells you what to read and what questions to answer.

---

### Step 3 — Identify evidence files

Read:
1. Every file you modified this turn
2. Every lifecycle file from Step 2 (`installed_by`, `removed_by`, `updated_by`, `documented_in`)
3. Up to 2 additional maintenance files — files that maintain lists, registries, or cleanup routines for the type of thing you just created/deleted
4. `.vibecheck/active_frameworks.json` if it exists — lists frameworks detected in the files you just changed. For each framework name listed, read `.claude/hooks/lib/frameworks/<name>.md` and apply its questions during Step 5. These are senior-dev reflexes for patterns that deserve explicit reasoning: retry behavior, rollback story, idempotency, visibility at 2am.

**Installer/uninstaller rule**: if a file is added to an installed, generated, or copied set (commands, hooks, lib files, routes, plugins), read both the installer path AND the uninstaller/cleanup path. This is the check that catches "you added the file but forgot to clean it up on uninstall."

**Dead-on-arrival rule**: if a new source file was created this turn (not an entry point, test, or config), grep for `import <module_name>` or `require('<filename>')` across the project. If zero results: flag DEAD_ON_ARRIVAL. Only flag after running the grep — never guess.

Only flag cross-file gaps if you actually read the maintenance file and confirmed the gap. Never guess.

Max 6 files total. Skip trivial-change short-circuit: if the change is a comment fix, typo, or config value tweak with no structural impact, you may skip Steps 3–5 and output `✅ Safe to continue` directly.

---

### Step 4 — Generate review questions

From the brief in Step 2, form specific questions to verify:

- **Lifecycle questions** (from project_map): "Is this new command in init.js copy list? update.js? uninstall.js? README?"
- **Convention questions** (from memory.known_conventions): "Does this follow the established pattern for X?"
- **Miss questions** (from memory.recent_misses): "Is this the same gap that was missed last time?"
- **Doc questions**: "Does this match what the project promises?"

---

### Step 5 — Verify each question against evidence

Read the evidence files from Step 3. For each question from Step 4: verified ✓ or gap found ✗.

---

### Step 6 — Write findings

**CRITICAL** — concrete exploit OR code that will definitely crash or corrupt data.

The catalog below lists common web-app patterns. **Do not treat it as a closed list.** Apply the critical bar to what this project actually does. Ask: *"If an attacker controlled this input / if this ran in prod today — what is the concrete, immediate impact?"* If the answer is credential theft, unauthorized action on behalf of a user, data corruption, or a definite crash — it is CRITICAL regardless of whether it matches a catalog pattern.

Common examples (not exhaustive):
- AUTH-01: Route reads/writes user data, no auth check before first DB call
- AUTH-02: Webhook endpoint parses body without signature verification (Stripe, Svix, GitHub)
- AUTH-03: Service-role or admin key used in a public/non-admin route
- DATA-02: Schema changed with no migration file
- DATA-04: Payment event processed without idempotency check (Stripe retries = double charge)
- Secret/credential hardcoded in source
- Exported function signature changed but callers not updated (ARCH-08)

**PITFALL** — works today, causes pain later:
- AUTH-04: Auth check after data fetch (check first, always)
- AUTH-06: Custom JWT when the project's auth library handles it
- ARCH-01: Service/factory/interface for a single DB call — delete it
- ARCH-03/04: Custom email or job queue instead of Resend/Inngest
- DEAD_ON_ARRIVAL: new file confirmed by grep to have no callers
- DATA-01: In-memory rate limiter or counter (dies on restart)
- DATA-08: No DB connection pooling in serverless deployment
- DATA-06: Read-then-write without transaction (race condition)
- Silent production side-effects — debug flags in config files shipped to all users
- Cross-file inconsistency — confirmed after reading the maintenance file

**HYGIENE** — missing something standard:
- `await` without try/catch in payment, auth, or DB paths (DATA-03)
- Non-trivial feature with no test file

**GOOD_TO_HAVE** — minor, never blocking:
- Missing rate limiting on public endpoints
- Missing input validation on user-facing forms

Full anti-pattern catalog (30 patterns with fix prompts) available via `/vibecheck-review`.

**Stage-aware judgment**: read `project_stage` from `memory.json` (set via `/vibecheck-stage`). If set, apply the questions and severity changes below — these aren't just escalations, they change what you *ask*.

`mvp` — pre-PMF, speed matters more than architecture:
- When you see ARCH-05 (service layers, event buses, multi-file abstractions for a single operation): ask explicitly — "Is this complexity solving a problem you already have, or one you're anticipating?" If anticipated: the fix is *deletion*, not simplification. Severity: **PITFALL** (not nice-to-have — overbuilding at MVP stage has a real cost: slower iteration, harder debugging, code you'll throw away anyway).
- DATA-07 (stored derived data), OPS-03..05: stay GOOD_TO_HAVE — not worth the bandwidth.

`prod` — real traffic, real users, real money:
- DATA-01 (in-memory counter or rate limiter): this IS broken right now, not "will break eventually." Every deploy resets it. With real traffic, the limit is already ineffective. Severity: **CRITICAL**.
- DATA-08 (no DB pooling): same — under real load, connections are already exhausting. Severity: **CRITICAL**.
- OPS-06 (AI route with no timeout on Vercel): users are already hitting gateway errors on slow LLM calls. Severity: **PITFALL**.

`growth` — between MVP and prod: use default severities, no changes.

**Severity for cross-file gaps** — use the artifact group's `must_check` / `nice_check` to decide:
- Relationship key in `must_check` (e.g. `removed_by`, `installed_by`) → **PITFALL**
- Relationship key in `nice_check` (e.g. `documented_in`) → **HYGIENE** or **GOOD_TO_HAVE**
- No group match → use your judgment

**DROP**: large files, console.log unless leaking secrets, naming style, anything already in existing findings, cross-file gaps you haven't confirmed by reading the other file.

**Already handled by static checks (never re-flag inline):**
- OPS-01: env var missing from .env.example — caught by `static_checks.py` via grep
- ARCH-07: new file with no callers — caught by `static_checks.py` via reverse-dep map

Finding format (append to `.vibecheck/findings.json`):
```json
{"id":"vg-NNN","severity":"CRITICAL|PITFALL|HYGIENE|GOOD_TO_HAVE","title":"under 100 chars","file":"relative/path:line","why":"concrete consequence, under 200 chars","fix_prompt":"paste-ready fix","status":"open","source":"live","detected_at":"ISO timestamp"}
```
Max 3 new findings. Zero is valid. Never include secret values.

Auto-resolve: for each open finding whose file you read, if issue is gone → set `status:"resolved"`, add `resolved_at`, `resolution_note:"auto-resolved"`.

---

### Step 7 — Self-heal project_map + update memory

**Upgrade group confidence** when you verify a lifecycle relationship exists in code:
- Read a lifecycle file (e.g. `bin/init.js`) and saw it copying `commands/*.md` → the `slash_commands` group's `installed_by` relationship is confirmed
- Upgrade confidence: `seeded → inferred → confirmed`
- Add a specific evidence note: `"bin/init.js copies commands/*.md in commandFiles array at line 156"`
- Increment `times_confirmed`

Do this by reading `project_map.json`, updating the matching group, and writing it back. Schema:
```json
{
  "confidence": "inferred",
  "times_confirmed": 1,
  "last_confirmed": "ISO",
  "evidence": ["bin/init.js copies commands/*.md in commandFiles array"]
}
```

**Add a new inferred group** when you discover a lifecycle relationship that isn't in any existing group:
```json
{
  "new_group_name": {
    "description": "...",
    "source_glob": "...",
    "installed_by": [...],
    "removed_by": [...],
    "must_check": ["installed_by", "removed_by"],
    "nice_check": ["documented_in"],
    "confidence": "inferred",
    "evidence": ["observed in bin/init.js at line N"],
    "times_confirmed": 1,
    "created_at": "ISO",
    "last_confirmed": "ISO"
  }
}
```

**Update memory.json**:
- New convention found → append to `known_conventions`
- Gap caught that matches a prior pattern → append to `recent_misses`

Read file → merge → write back.

---

### Step 8 — Dev tip + verdict

After the security/correctness check, scan for:
- No tests for new feature → "No tests here — if this breaks in prod, you'll be debugging blind."
- New file added, nothing imports it (confirmed by grep) → "Nothing imports this yet — wire it up now or you'll forget it exists."
- New endpoint not wired to any caller → "This endpoint exists but nothing calls it — dead code waiting to happen."
- Big change (5+ files) → "This touches N files — hard to review, harder to roll back."
- Changed behavior without updating callers → "This changes existing behavior. Callers not updated will break silently."
- Schema change with no migration → "Schema changed but no migration file — fails in every environment that's not yours."
- No git commit, large change → "Commit now. One crash and this is gone."

Max 2 tips. Skip if not applicable.

**Verdict decision rule:**
- Any CRITICAL → `❌ Fix before shipping`
- Any PITFALL, no CRITICAL → `⚠️ OK for MVP, not prod`
- HYGIENE / GOOD_TO_HAVE only, or clean → `✅ Safe to continue`

**Footer** (write at the very end of your response):
```
---
VibeCheck: [verdict]  [· 🔴 N critical · ⚡ N pitfalls · 🧹 N hygiene — omit zero categories]
🧪 Before shipping: [specific thing to verify — name the exact flow, command, or edge case]
💡 [dev tip — one sentence, consequence-first — skip if nothing applies]
```

The `🧪` line must be specific. Not "add tests" — name what to test: "run `/vibecheck uninstall` and verify no command files remain" or "send a webhook with a forged signature and verify it's rejected."

Commands: `/vibecheck` · `/vibecheck <id>` · `/vibecheck-resolve <id>` · `/vibecheck-scan` · `/vibecheck-review` · `/vibecheck-stage`
