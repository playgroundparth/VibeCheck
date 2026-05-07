# Project

## Context Capture — MANDATORY triggers

You MUST append to `.vibecheck/timeline.json` BEFORE responding when ANY of these happen:

1. **Error resolved** — you fixed a bug or unblocked something that was failing
2. **Architecture/design decision** — a non-obvious choice was made (why matters, not just what)
3. **User preference discovered** — user corrected your approach, style, or rejected something
4. **Significant task completed** — multi-step feature or refactor finished
5. **20+ tool calls without a store** — write a progress summary

Do this BEFORE the rest of your response. Not after. Not "I'll note that." Write it now.

Do NOT store: trivial details, build logs, git status, anything already in CLAUDE.md.

### Format — append one entry to `.vibecheck/timeline.json` events array:
```json
{"ts":"ISO-timestamp","type":"error-resolved|decision|preference|task-completed|progress","summary":"what happened and why it matters","importance":"high|critical"}
```

To append: Read `timeline.json` (or treat as `{"events":[]}` if missing), add the entry to `events`, keep last 50 entries, write back.

---

## Engineering standards — apply to every response

These are not suggestions. A senior dev would catch every one of these in code review. Apply them before shipping any change.

**Tests must verify correctness, not just execution.**
`expect(result).toBeDefined()` is not a test — it confirms the code didn't throw, nothing more. Every test must assert specific output values. Every test must include at least one case where wrong input produces wrong output. Never mock the system under test. Disjunctive assertions (`assert.ok(a || b)`) are a smell — split them into separate tests so failures are actionable. If you can't write a meaningful assertion, say so — don't write a test that gives false confidence.

**Don't catch exceptions to make tests pass.**
If a test fails, fix the code. Don't wrap the failing call in try/catch to silence it. Don't add defensive null checks that hide a real bug. Don't widen a type from `User` to `User | null` because the call site sometimes returns null when it shouldn't. Hiding the failure doesn't resolve it — it just makes it harder to find later.

**Don't expand scope mid-task.**
When asked to fix bug X, fix bug X. Don't refactor adjacent code, rename variables for "clarity," reformat files, or add features that "make sense while we're here." Each unrelated change makes the diff harder to review and the fix harder to revert. If you notice something else worth doing, say so explicitly — don't do it without asking.

**Remove dead code. Don't comment it out.**
Unused imports, commented-out blocks, functions with no callers — delete them. Git is the backup. Commented-out code is a lie: it implies it might come back, which it won't, and it makes the real code harder to read. If something is genuinely experimental, say so in a comment explaining *why* it's there and what condition would bring it back.

**Separate "changed" from "verified" in your summary.**
When summarizing work, distinguish the two explicitly: "Changed: added retry logic to the fetch handler. Verified: ran integration test, confirmed retries fire on 503." Don't list items as verified if you only inspected them visually. Don't mark something done if you only changed it.

**Say what to run to confirm the fix works.**
Don't claim something is fixed without a verification step. The verification must be runnable locally, must fail when the bug is present, and must pass when the fix is applied. After every non-trivial change: name the command, request, or flow. If it requires a specific condition (a user role, a queue event, a race condition), say how to reproduce it. "Deploy and test in prod" is not a verification plan.

**Name every caller when you change a function signature, then update them all.**
If you rename a function, change its parameters, or alter its return shape — grep for every caller and update them in the same response. Don't leave the codebase half-migrated, with some callers on the old API and some on the new. For typed languages: a clean type-check is the floor, not proof — run the actual code path.

**Never claim something is faster or more efficient without measuring it.**
"This is more performant" with no benchmark is a guess dressed as a fact. Don't add caching, pre-computation, or memoization unless you have a profile showing where the time is going. The inverse applies too: don't assume something is slow without measuring — premature pessimization is just as wrong. If you're choosing an approach for performance reasons, state the assumption and how to validate it.

**Document non-obvious choices at the point of decision.**
When you pick X over Y for a reason that isn't obvious from the code, write a comment explaining why. Decisions discussed in chat are not durable — if a tradeoff was resolved, write it in the code or repo. When you discover a constraint or limitation that will affect future work, document it where future-you will find it. Silence gets re-litigated.

**Check existing code before adding something new.**
Before writing a new utility, check `lib/`, `utils/`, `helpers/` — it may already exist. Before recommending a library, check `package.json`, `requirements.txt`, `pyproject.toml`, or `Cargo.toml`. Internal duplication is as harmful as an unnecessary dependency: two `formatDate()` implementations means two places where bugs live.

**Match the codebase's style before writing new code.**
Before writing anything, look at how nearby code handles the same kind of thing — imports, error handling, naming, file organization. If the codebase uses `snake_case` for functions, don't introduce `camelCase`. If it uses `Result<T>` for fallible operations, don't throw exceptions. If it uses a particular pattern for async calls, match it. Style drift compounds across sessions: code that's locally clean but globally inconsistent creates a cleanup pass that shouldn't have been necessary.

**Read generated files before treating them as done.**
When a tool generates output — a database migration, an OpenAPI spec, a Prisma schema diff, a snapshot file — open it and read it before committing. Don't trust that the generator produced what you intended. Generated migrations regularly drop indexes, rename columns, or include unintended schema changes from partially-resolved conflicts. "The command completed successfully" means the tool ran, not that the output is correct.

---

## VibeCheck (active) — evidence-driven inline check

After ANY response where you used Write, Edit, or MultiEdit tools, run this at the END of your response.

**Short-circuit**: if the `[VibeCheck Detection]` block says "No issues detected" AND the change is a comment fix, typo, or config value tweak with no structural impact → output `✅ Safe to continue` and stop.

---

### Step 1 — Read the detection evidence

The PostToolUse hook already ran detection against the changed file(s). Look for a `[VibeCheck Detection]` block in the system context injected before this response.

- If the block is present: work through each `EVIDENCE-NNN` item below
- If no block (hook may have missed a rapid edit): do a brief self-check using the security rules below — treat it as if you had a single LOW-confidence item for each changed file

**Your role is confirmation, not detection.** The hook detected patterns. You confirm whether they're real by reading the actual code. Never invent evidence that wasn't in the detection block.

---

### Step 2 — Confirm each evidence item

For each `EVIDENCE-NNN` item in the detection block:

1. **Read the cited `file:line`** (you have the exact path and line number)
2. Apply the confidence rule:
   - **`confidence:high`** — write the finding unless you see a clear mitigation in the code you read
   - **`confidence:medium`** — confirm the issue is real before writing; if clear mitigation is present, skip
   - **`confidence:low`** — only write the finding if the code you read clearly demonstrates the problem
3. **Never write a finding for evidence you can't confirm by reading actual code**

For lifecycle/cross-file issues (new file added, installer change, etc.): grep or read the relevant lifecycle file to confirm before writing.

---

### Step 3 — Write findings

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

**DROP**: large files, console.log unless leaking secrets, naming style, cross-file gaps you haven't confirmed by reading the other file.

**No severity stacking** — if a file already has an open CRITICAL or PITFALL finding, do not add a HYGIENE or GOOD_TO_HAVE for the same underlying issue on that file. One finding per issue. If something is already captured at higher severity, skip it.

**Already handled by static checks (never re-flag inline):**
- OPS-01: env var missing from .env.example — caught by `static_checks.py` via grep
- ARCH-07: new file with no callers — caught by `static_checks.py` via reverse-dep map

Finding format (append to `.vibecheck/findings.json`):
```json
{"id":"vg-NNN","severity":"CRITICAL|PITFALL|HYGIENE|GOOD_TO_HAVE","title":"under 100 chars","file":"relative/path:line","why":"concrete consequence, under 200 chars","fix_prompt":"paste-ready fix","status":"open","source":"live","detected_at":"ISO timestamp"}
```
Max 3 new findings. Zero is valid. Never include secret values in `why` or `fix_prompt`.

---

### Step 4 — Auto-resolve + self-heal project_map

**Auto-resolve**: for each open finding (from `.vibecheck/findings.json`) whose file you read this turn, if the issue is gone → set `status:"resolved"`, add `resolved_at`, `resolution_note:"auto-resolved"`.

**Self-heal project_map** (optional, only when lifecycle files are involved):

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

### Step 5 — Dev tip + verdict

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
