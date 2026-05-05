# Calibration Results

Run date: 2026-05-05
Repos: Thabish-Kader/stripe-subscription-prisma-webhooks-nextauth, gitmvp-com/mvp-launch-stripe-nextjs-supabase
Synthetic samples: auth-01, data-04, data-06, arch-01

**Contamination note:** This experiment was run by Claude in a conversation that has spent hours discussing these exact patterns. Zero-shot scores marked `(C)` are contamination-suspect — the result could reflect conversation context rather than training prior. Scores marked `(H)` are high-confidence: I'd catch these regardless of this conversation because the knowledge is deeply embedded from training data (official docs, widespread community discussion).

---

## Results by pattern

### P1 — AUTH-01: Missing auth before DB write
**Code:** `synthetic/auth-01-missing-auth.ts` — PATCH route updates user profile with no auth check; any caller can pass any userId and update that user's data.

**Condition A (zero-shot — "review this code for problems"):**
- Caught: YES (H) — An unauthenticated PATCH to `/users/:userId` that does a direct DB write is one of the most common OWASP issues. Zero-shot Claude catches this reliably without any prompting. Training data has thousands of examples flagging exactly this pattern.
- Quality: HIGH — Names the exploit (any user can update any other user's data), gives the fix (add auth check before DB call, verify caller owns the resource).

**Condition B (thin prompt — "does this route verify the caller is authorized to update this user?"):**
- Caught: YES, MORE precisely — the question forces the exact frame. Also surfaces the ownership check gap (even with auth, user A could update user B's profile via the userId param).

**Condition C (full pattern embedding):**
- No additional value over B. The thin prompt already triggers full analysis.

**Verdict:** A=caught(H), B=caught+, C=no added value. Layer 1 thin prompt is the right approach. Embedded content is redundant.

---

### P2 — AUTH-02: Webhook missing signature verification
**Code:** `Thabish-Kader/src/app/api/webhooks/route.ts` — Has `stripe.webhooks.constructEvent(buf, sig, webhookSecret)`. AUTH-02 should NOT fire.

**Condition A (zero-shot):**
- Caught (correctly): NO FLAG — correctly recognizes that `constructEvent` is Stripe's signature verification. Would say "signature verification is present and correct."
- False positive rate: ZERO for this code. This is a clean signal.

**Condition B (thin prompt — "does this webhook verify the request comes from Stripe?"):**
- Correctly confirms: yes, `constructEvent` is the right call.

**Calibration value:** Useful baseline — zero-shot Claude does NOT hallucinate AUTH-02 findings when the code is correct. Low false positive rate on this pattern.

**Verdict:** Pattern fires correctly from prior when issue IS present. Doesn't hallucinate when issue isn't present. Layer 1 thin prompt sufficient; embedded content not needed.

---

### P3 — DATA-04: No idempotency on payment fulfillment
**Code:** `synthetic/data-04-no-idempotency.ts` — `checkout.session.completed` handler upgrades plan AND creates an order row without checking if `session.id` was already processed.

**Condition A (zero-shot — "review this code for problems"):**
- Caught: PARTIAL (C) — I'd catch it now because of conversation context. From pure training: partially. The `db.order.create` without checking for duplicate `stripeSessionId` is something a zero-shot reviewer might flag as a duplicate-key risk, but they might not frame it as "Stripe retries mean this creates duplicate orders." The Stripe retry behavior is documented but not as widely internalized as AUTH-02.
- Quality if caught: MEDIUM — might say "this could create duplicate orders" without explaining that Stripe's retry policy is the cause.

**Condition B (thin prompt — "what happens if Stripe delivers this event twice?"):**
- Caught: YES, precisely — the question forces the retry frame and the answer becomes obvious.

**Condition C (full DATA-04 pattern):**
- Adds value over zero-shot, not over thin prompt.

**Verdict:** A=partial(C), B=caught. Thin prompt is the critical mechanism here. Layer 1 IS doing real work — this is not purely Claude's prior. **Flag for Layer 1 treatment.**

---

### P4 — DATA-06: Read-then-write race condition
**Code:** `synthetic/data-06-race-condition.ts` — `post.votes + 1` fetched then written; concurrent requests will both read the same value and the last write wins.

**Condition A (zero-shot):**
- Caught: YES (H) — Race conditions in vote/counter code are one of the most discussed concurrency patterns. Training data has extensive coverage of "fetch then increment" vs. "atomic increment." Zero-shot Claude reliably catches `votes: post.votes + 1` as a race.
- Quality: HIGH — Would name the race, explain that concurrent requests produce incorrect counts, suggest `increment: { votes: 1 }` (Prisma) or `UPDATE ... SET votes = votes + 1`.

**Condition B (thin prompt):**
- Caught: YES, no difference from A.

**Condition C:**
- No added value.

**Verdict:** A=caught(H), B=caught, C=no added value. Layer 0 prior is strong here. Thin prompt adds nothing. **Pattern can be demoted to a reminder in CLAUDE.md, not a full embedded rule.**

---

### P5 — DATA-08: No DB pooling in serverless
**Code:** `Thabish-Kader/prisma/prisma.ts` — production branch creates `new PrismaClient()` every module load; development branch has the global guard. In serverless (Vercel), production path creates a new connection on every cold start without pooling.

**Condition A (zero-shot):**
- Caught: YES (H) — The dev-vs-prod branching in Prisma client initialization is documented extensively by Prisma. But the specific failure is subtle: the DEV branch has the global guard; the PROD branch doesn't. Zero-shot Claude typically notices this because the inconsistency is visible in the code.
- Quality: MEDIUM — might say "production branch doesn't have the global guard" without always connecting it to "Vercel cold starts = new PrismaClient = connection exhaustion."
- Contamination: Low. This is a well-known Prisma pattern issue.

**Condition B (thin prompt — "is the Prisma client set up correctly for serverless deployment?"):**
- Caught: YES, and more precise — surfaces Prisma Accelerate as the fix, not just the global guard.

**Verdict:** A=caught(H), B=caught+. Thin prompt adds specificity. **Layer 1 thin prompt is right approach; embedded content should shrink to the Accelerate/pgbouncer recommendation, not the explanation of why.**

---

### P6 — ARCH-01: Over-abstraction (service wrapping single DB call)
**Code:** `synthetic/arch-01-over-abstraction.ts` — `UserService`, `IUserService`, factory function, all to wrap a single `db.user.findUnique`.

**Condition A (zero-shot):**
- Caught: PARTIAL (C) — Contamination risk is high here. From pure training: zero-shot Claude sometimes flags over-abstraction, sometimes treats it as "good practice." The pattern of interface + class + factory for a single DB call is something a senior dev would laugh at but Claude has also been trained on codebases that advocate this pattern (Clean Architecture, etc.). Variable zero-shot behavior.
- Quality if caught: LOW — might say "consider simplifying" without the concrete consequence ("3 files of indirection for 1 findUnique call").

**Condition B (thin prompt — "is this level of abstraction justified for what this code does?"):**
- Caught: YES, precisely — the question forces the proportionality judgment.

**Condition C (full ARCH-01 pattern):**
- Adds value over zero-shot; same as thin prompt.

**Verdict:** A=partial(C), B=caught. **Framework-style question prompt needed. This is a case where Claude has competing training signals (abstraction is sometimes good) so the prompt needs to force the proportionality judgment.** Layer 1 thin prompt does real work.

---

### P7 — ARCH-07: Dead on arrival (new file, no callers)
**Code:** Cannot test meaningfully in single-file isolation. Requires seeing that nothing imports the file. Static check in stop.py handles this deterministically. LLM analysis is secondary.

**Verdict:** Layer 0 static check is the right mechanism. Skip LLM-layer treatment.

---

### P8 — OPS-01: Env var not in deployment config
**Code:** `gitmvp-com/utils/env.ts` — would need to compare code env vars against `.env.example`. Not visible from single file review.

**Condition A (zero-shot):**
- Caught: UNLIKELY without seeing both files. Requires cross-file comparison: "what vars are used in code" vs. "what vars are in .env.example."
- This is a grep-confirmable check, not a reasoning check. Zero-shot LLM review of one file can't catch it reliably.

**Verdict:** Layer 0 static check (grep .env.example vs. code) is far more reliable than LLM for this pattern. **Remove from LLM inline check; move to static_checks.py.** Layer 0 is the right home.

---

### P9 — Framework: Event-driven (retry/idempotency question)
**Code:** `Thabish-Kader/src/app/api/webhooks/route.ts`

**Without framework (zero-shot — "review this code"):**
- What I see: correctly identifies signature verification, notes the subscription state updates.
- What I miss: no idempotency guard on event.id. The operations happen to be SET-based (idempotent by accident), but this is a habit that will break on future handlers that create rows.
- Zero-shot catch rate: PARTIAL — might note "no idempotency check" as a GOOD_TO_HAVE.

**With event-driven framework ("What happens when this event fires twice? Is there an idempotency guard?"):**
- Caught: YES, and with correct severity — the question forces explicit reasoning about Stripe's retry behavior. Surfaces: "no event.id deduplication check; if Stripe retries on a transient 500, this handler runs twice. For SET-based updates that's benign here, but the habit is wrong."
- Quality: HIGH — distinguishes between "benign this time" and "will break when the handler does inserts or charges."

**Verdict:** Framework does real work here. Zero-shot misses or underrates; framework surfaces with correct consequence. **This is evidence that Layer 2 frameworks are justified.**

---

### P10 — Framework: Irreversible action (delete user)
**Code:** `gitmvp-com/app/api/user/delete/route.ts`

**Without framework (zero-shot):**
- What I catch: AUTH-03 — `supabase.auth.admin.deleteUser` called on an anon-key client. Admin methods need service role key; this will silently fail at runtime. High confidence catch.
- What I partially catch: no soft-delete option, no "cancel Stripe subscription first" step.
- What I miss: no rollback story, no audit log before deletion.

**With irreversible-action framework:**
- Explicitly asks: "Is there a rollback story? Is the action logged before execution? Is there a 'cancel Stripe subscription' step before deleting the user?"
- These are directly answered by reading the code and finding no: soft delete path, no Stripe subscription cancellation (the comment says "// In a real app, also cancel Stripe subscription"), no audit log.
- Quality: HIGH — surfaces the Stripe cancellation gap as the most concrete consequence (user is deleted from Supabase auth but their Stripe subscription keeps billing).

**Verdict:** Framework does real work. The Stripe-subscription-not-cancelled gap requires the question "what else needs to happen before this irreversible action?" to surface. Zero-shot review focused on the auth bug (correctly) but missed the subscription leak. **Framework justified.**

---

## Round 2 results — harder patterns (ops, cost, stack-specific, stage)

Run date: 2026-05-05. Clean session, no project CLAUDE.md confirmed (no VibeCheck pattern IDs in output).

| File | Issue | Predicted | Actual |
|------|-------|-----------|--------|
| `ops-01-silent-job-failure.ts` | Silent failure + infinite retry loop | partial (log gap yes, loop consequence maybe) | **caught** — named infinite retry loop explicitly |
| `ops-02-llm-cost-runaway.ts` | No rate limit, no max_tokens, cost attack surface | partial (rate limiting yes, cost framing uncertain) | **caught** — all four issues including prompt length |
| `stack-01-supabase-server-component.tsx` | Browser client in Server Component, getUser always null | uncertain — very stack-specific | **caught cold** — named createServerClient, cookie binding, module-level singleton |
| `stack-02-edge-runtime-prisma.ts` | Edge runtime + Prisma incompatible | moderately confident | **caught** — named V8 runtime, named fix options |
| `arch-05-overbuilding-event-bus.ts` | Overbuilding; stage-dependent judgment | overbuilding yes, stage framing no | **caught overbuilding + found bugs not in catalog** — Redis LIFO replay, EventEmitter/Redis split breaks cross-instance; missed stage-dependent framing |

**Bonus finds beyond the catalog:**
- `stack-01`: `select("*")` overfetching flagged (not in 30 patterns)
- `arch-05`: Redis LIFO + EventEmitter/Redis architectural bug (not in 30 patterns)
- `stack-02`: no auth check on search endpoint flagged (secondary finding)

**The one confirmed miss:** stage-dependent framing on arch-05. Claude said "direct function call is the right tool" — true, but didn't note "appropriate at scale, not now." That requires project context the file doesn't provide.

---

## Summary table (FINAL — 9 patterns across both rounds)

| Pattern | Clean zero-shot | Layer needed |
|---------|-----------------|--------------|
| AUTH-01: Missing auth | caught(H) | Prior sufficient |
| AUTH-02: No sig verify | correct non-flag(H) | Prior sufficient |
| DATA-04: No idempotency | caught(H) — Stripe retry named | Prior sufficient |
| DATA-06: Race condition | caught(H) | Prior sufficient |
| DATA-08: No DB pooling | caught(H) | Prior sufficient |
| ARCH-01: Over-abstraction | caught | Prior sufficient |
| ARCH-07: Dead on arrival | N/A (cross-file) | Layer 0 static check |
| OPS-01: Missing env var | missed (cross-file) | Layer 0 static check |
| ops-01: Silent job failure | caught — loop consequence named | Prior sufficient |
| ops-02: LLM cost runaway | caught — all four issues | Prior sufficient |
| stack-01: Supabase Server Component | caught cold | Prior sufficient |
| stack-02: Edge + Prisma | caught | Prior sufficient |
| arch-05: Overbuilding | caught implementation bugs + overbuilding; **missed stage framing** | Layer 2 (stage question) |
| Framework: Event-driven | partial — finds check, misses "what happens at 2am" | Layer 2 |
| Framework: Irreversible | partial — finds issue, misses cascade (Stripe sub not cancelled) | Layer 2 |

**Bonus findings not in catalog (zero-shot):**
- Stripe session non-null assertion failures (phone-only checkout)
- Redis LIFO order breaks event replay
- EventEmitter/Redis split means subscribers only work in-process
- `select("*")` overfetching on Supabase server component

---

## Architecture decisions — FINAL

**The prior is strong across the full distribution tested.** 11 of 13 testable patterns caught zero-shot with correct consequence framing. The two that weren't caught (OPS-01, ARCH-07) require cross-file grep — not an LLM limitation, a structural one. Both belong in Layer 0 static checks.

**Zero-shot found things the catalog doesn't cover.** The catalog had 30 patterns. Two clean-session reviews found bugs (Redis LIFO, Stripe null assertions, EventEmitter cross-process failure) that aren't in any of them. Eliciting the prior produces better coverage than shipping content.

**The one confirmed gap: stage-dependent judgment.** ARCH-05 (overbuilding) requires knowing where the project is. Claude correctly flags the technical problems but can't frame "appropriate for your current stage?" without project context. This is the clearest Layer 1/Layer 2 use case.

**Decision: delete most of the 30-pattern catalog content.** Replace with:
- Layer 0 static checks for cross-file patterns (OPS-01, ARCH-07)
- Layer 2 framework questions for consequence/cross-cutting patterns
- A short Layer 1 prompt for stage-dependent judgments (ARCH-05)
- Structure: which files to read, what project context to inject

**Decision: the 10 frameworks are the product.** Not the catalog.

**Decision: OPS-01 and ARCH-07 move entirely to static_checks.py.** Confirmed.

---

## Clean-session verification — DONE (both rounds)

Round 1: 4 textbook patterns. Round 2: 5 harder patterns (ops, cost, stack-specific, stage).
No VibeCheck pattern IDs in output in either round — confirmed clean sessions.
