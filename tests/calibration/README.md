# Calibration Experiment

**Run this before committing to the v2 architecture.**

Tests where Claude's prior is strong vs. weak across the 30 anti-patterns. Results determine how much embedded content Layer 1 needs vs. how much to delegate to Claude's prior.

## Setup

Pick 10 patterns from the catalog. Pick or write real code samples that have the issue. Run three conditions per pattern.

## The three conditions

**Condition A — Zero-shot**
Prompt: "Review this code for problems."
(No mention of patterns, no hints about what to look for)

**Condition B — Thin prompt (Layer 1 question form)**
Prompt: "Does [specific question about the relevant concern]? [one sentence of context about what this code does]"
Example for AUTH-01: "Does this route check authentication before accessing user data?"

**Condition C — Full embedded content (current approach)**
Prompt: [current full pattern description with trigger, severity, consequence, fix prompt]

For each condition: does Claude catch the issue? Rate:
- `caught` — correctly identifies the issue, names the consequence, gives a usable fix
- `partial` — identifies there's an issue but consequence or fix is vague/generic
- `missed` — does not flag the issue

## Patterns to test (10 representative samples)

| # | Pattern | Code sample to use | What to look for |
|---|---------|-------------------|------------------|
| 1 | AUTH-01 (no auth check) | Route that does `prisma.user.findMany()` without `auth()` first | Does it flag missing auth? |
| 2 | AUTH-02 (no webhook sig verify) | Stripe webhook that calls `req.json()` before `constructEvent` | Does it flag sig bypass? |
| 3 | DATA-04 (no idempotency) | Stripe `payment_intent.succeeded` handler with no event ID check | Does it flag double-charge risk? |
| 4 | DATA-06 (read-then-write race) | `count = await db.count(); await db.update({count: count+1})` | Does it flag the race? |
| 5 | DATA-08 (no pooling in serverless) | `new PrismaClient()` at top level in a Next.js route | Does it flag connection exhaustion? |
| 6 | ARCH-01 (over-abstraction) | `UserService` class with one method wrapping one `findUnique` | Does it flag unnecessary indirection? |
| 7 | ARCH-07 (dead on arrival) | A new `lib/formatter.ts` that nothing imports | Does it flag the dead code? |
| 8 | OPS-01 (missing env var) | `process.env.NEW_API_KEY` in code, absent from `.env.example` | Does it flag the missing var? |
| 9 | Any framework pattern — event-driven | Queue consumer that returns 200 before completing work | Does it flag the retry/idempotency risk? |
| 10 | Any framework pattern — irreversible | Email send with no dedup/idempotency check | Does it flag double-send risk? |

## Decision rule

| A (zero-shot) | B (thin prompt) | Conclusion |
|---|---|---|
| ≥8/10 caught | ≥8/10 caught | Prior is strong. Layer 1 thin prompts are sufficient. Most embedded content is redundant. |
| ≤5/10 caught | ≥8/10 caught | Prompting matters. Layer 1 question prompts are the key mechanism. Embed them, not content. |
| ≤5/10 caught | ≤5/10 caught | Prior is weak for this category. Embedded content (Layer 4) required. Note which patterns. |

Do this per-pattern, not just in aggregate. A pattern where A=caught but B=caught means question prompts are free; a pattern where A=missed and B=caught means Layer 1 is doing real work; a pattern where A=missed and B=missed means Layer 4 is needed.

## After the experiment

Fill in this table:

| Pattern | A score | B score | Layer needed |
|---------|---------|---------|--------------|
| AUTH-01 | | | |
| AUTH-02 | | | |
| ... | | | |

Then:
- "Layer 1 sufficient" patterns: convert catalog entry to question prompt, slim it down
- "Layer 1 needed" patterns: keep question prompt, no embedded content
- "Layer 4 needed" patterns: keep full embedded content, flag for verified-source treatment

This table is the actual output of the experiment. Everything else in v2 is built from it.
