# Golden Examples — Behavioral Spec for the LLM Layer

These files define the expected behavior of VibeCheck's inline analysis for representative scenarios. They are **not programmatically asserted** — they are the specification that informs prompt writing, manual QA, and future eval harnesses.

Each file follows the same structure:

- **Scenario** — what the developer just built
- **What Changed** — files modified this turn
- **Evidence Files VibeCheck Should Read** — what the 8-step pipeline should load (from project_map or heuristic)
- **Evidence Found** — the relevant content in those files
- **Expected VibeCheck Output** — the exact finding fields and footer that should be produced
- **Global Invariant** — confirms verdict is present and answers "can I continue?"
- **What Must NOT Happen** — false positives, wrong verdicts, and anti-patterns to guard against

---

## Global Invariant (applies to every golden)

**Every output must answer: "Can I continue?"**

This means:
1. **Verdict is mandatory.** Every VibeCheck footer must contain one of `❌ Fix before shipping`, `⚠️ OK for MVP, not prod`, or `✅ Safe to continue`. A footer without a verdict is a regression.
2. **No floating findings.** Findings without a verdict are not valid output — the developer needs a decision, not a list.
3. **Verdict matches the worst finding.** CRITICAL → ❌. PITFALL → ⚠️. HYGIENE/GOOD_TO_HAVE/nothing → ✅.

---

## Cases

| File | Scenario | Expected Verdict |
|------|----------|-----------------|
| [`01`](01-command-lifecycle-drift.md) | New command file; uninstall doesn't include it | ⚠️ OK for MVP, not prod |
| [`02`](02-command-lifecycle-clean.md) | New command file; all lifecycle scripts updated | ✅ Safe to continue |
| [`03`](03-webhook-signature-bypass.md) | Stripe webhook with no signature check | ❌ Fix before shipping |
| [`04`](04-overengineered-custom-auth.md) | Custom JWT when Supabase auth is available | ⚠️ OK for MVP, not prod |
| [`05`](05-safe-mvp-shortcut.md) | Pure utility function with tests, no risk surface | ✅ Safe to continue |
| [`06`](06-unnecessary-abstraction.md) | Service/interface/factory for a single DB call | ⚠️ OK for MVP, not prod |
| [`07`](07-intentional-mvp-tradeoff.md) | In-memory rate limiter, explicitly labeled MVP | ⚠️ OK for MVP, not prod |
| [`08`](08-no-code-change.md) | README-only update, no code changed | ✅ Safe to continue (minimal output) |

---

## Evidence Anchoring (applies to every finding)

Every finding must include:
- `"file": "path/to/file:line"` — exact location of the problem
- `"files_read": [...]` — which files were actually read to produce this finding

A finding that doesn't name its evidence is unverifiable. If VibeCheck produces a cross-file finding (e.g., uninstall.js missing a file), `files_read` must include both the changed file and the maintenance file that was checked. This is how you know the 8-step pipeline is actually running — not just reasoning about file names.

---

## Anti-Patterns (regression risks across all goldens)

These are the failure modes most likely to appear after prompt changes. Every golden's "What Must NOT Happen" section catches a subset of these.

**Verdict failures:**
- ❌ Missing verdict — the footer ends with finding counts but no decision
- ❌ Wrong verdict tier — PITFALL producing ❌, or CRITICAL producing ⚠️
- ❌ Verdict without evidence — ❌ verdict with no CRITICAL finding in the output

**Generic language:**
- ❌ "Consider adding…" — VibeCheck makes statements, not suggestions
- ❌ "You may want to…" — same problem
- ❌ "It might be worth…" — same problem
- ❌ Consequences described as hypothetical when they're certain

**Missing evidence:**
- ❌ Cross-file finding with no `files_read` — means the pipeline skipped the check
- ❌ Finding with no `file:line` — unactionable
- ❌ `🧪` line not tied to actual code — e.g., "test the endpoint" instead of naming the specific scenario

**Over-triggering:**
- ❌ Finding produced without reading evidence (README change, pure utility)
- ❌ HYGIENE finding when a CRITICAL exists — CRITICAL takes full focus
- ❌ nice_check gap reported when must_check gap exists
- ❌ Manufacturing a finding to seem thorough

**Tone failures:**
- ❌ Praise in the same response as a PITFALL
- ❌ Moralizing about intentional tradeoffs (labeled MVP code)
- ❌ Cheerleading ("great work keeping tests updated")
- ❌ Softening a CRITICAL with "consider" or "might"

---

## How to Use

**Prompt tuning** — if a scenario produces the wrong verdict or a false positive, update `CLAUDE.template.md` and re-verify manually against the golden.

**Manual QA** — before shipping a CLAUDE.md change, walk through each golden scenario by hand and check verdict, finding fields, and `🧪` specificity.

**Future eval harness** — these become labeled examples for an automated eval that runs VibeCheck against synthetic diffs and scores output against the golden contract.
