# Golden Examples — Behavioral Spec for the LLM Layer

These files define the expected behavior of VibeCheck's inline analysis for representative scenarios. They are **not programmatically asserted** — they are the specification that informs prompt writing, manual QA, and future eval harnesses.

Each file follows the same structure:

- **Scenario** — what the developer just built
- **What Changed** — files modified this turn
- **Evidence Files VibeCheck Should Read** — what the 8-step pipeline should load (from project_map or heuristic)
- **Evidence Found** — the relevant content in those files
- **Expected VibeCheck Output** — the exact finding fields and footer that should be produced
- **What Must NOT Happen** — false positives and wrong verdicts to guard against

## Cases

| File | Scenario | Expected Verdict |
|------|----------|-----------------|
| `01-command-lifecycle-drift.md` | New command file, uninstall doesn't include it | ⚠️ OK for MVP, not prod |
| `02-command-lifecycle-clean.md` | New command file, all lifecycle scripts updated | ✅ Safe to continue |
| `03-webhook-signature-bypass.md` | Stripe webhook with no signature check | ❌ Fix before shipping |
| `04-overengineered-custom-auth.md` | Custom JWT when Supabase auth is available | ⚠️ OK for MVP, not prod |
| `05-safe-mvp-shortcut.md` | Pure utility function with tests, no risk surface | ✅ Safe to continue |

## How to Use

**Prompt tuning** — if a scenario produces the wrong verdict or a false positive, update `CLAUDE.template.md` rules and re-verify manually against the golden.

**Manual QA** — before shipping a CLAUDE.md change, walk through each golden scenario by hand and check that the output matches.

**Future eval harness** — these become the labeled examples for an automated eval that runs VibeCheck against synthetic diffs and scores the output.
