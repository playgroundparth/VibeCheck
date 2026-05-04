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

After ANY response where you used Write, Edit, or MultiEdit tools, do this at the END of your response — after completing the user's request:

1. Read `.vibecheck/findings.json` to get existing findings and next ID
2. Read the files you just modified. Then identify up to 2 **maintenance files** — files that
   maintain lists, registries, or cleanup routines for the type of thing you just created or
   deleted. Read those too. Rules for which maintenance files to read:
   - **Installer/uninstaller rule**: if a file is added to an installed, generated, or copied set
     (commands, hooks, lib files, routes, plugins), read both the installer path (init/update
     script) AND the uninstaller/cleanup path. This catches the case where you added the file
     but forgot to clean it up on uninstall.
   - Added a command/route/feature file → read install scripts, update copy lists, AND uninstall cleanup lists
   - Added a new item to a collection → read any file that registers, indexes, or removes that collection type
   - Changed a function signature → read callers that weren't modified this turn
   - Deleted or renamed something → read any file that references it by name
   Only flag a cross-file gap if you actually read the maintenance file and confirmed the gap. Never guess.
3. Review for issues (rules below)
4. Write new findings to `.vibecheck/findings.json`
5. Auto-resolve: for each open finding whose file you read, if issue is gone → set `status:"resolved"`, add `resolved_at`, `resolution_note:"auto-resolved"`
6. **Always end your response with a VibeCheck footer** (format below)

---

### Review Rules

**CRITICAL** — concrete exploit OR code that will definitely crash or corrupt data in production:
- Route handles user data without auth check
- User input in DB query (SQL injection)
- User-controlled path in file read/write (path traversal)
- Webhook/payment endpoint without signature verification
- API response leaks data the caller shouldn't see
- Secret/credential hardcoded in source
- Logic that will definitely crash or lose data (off-by-one on deletion, wrong condition on write, missing null check on a field that will be null)

**PITFALL** — works today, causes pain later. Covers architectural traps AND decision-level mistakes:
- In-memory rate limiting or counters (won't survive restarts)
- Custom auth/JWT instead of using a library (REINVENTING)
- New feature built on top of code that is already broken
- OVERBUILDING — complexity that exceeds what this stage of the project needs (caching before load is proven, microservices for a solo project, abstraction layer with one implementor)
- REINVENTING — building something that already exists and works better (custom JWT, custom email sending, custom file storage, custom queues)
- WRONG ABSTRACTION — the structure will resist the next obvious change (wrong layer, wrong boundary, the interface that can't grow)
- Cross-file inconsistency — item added to a collection but installer, uninstaller, or update list not synced (only flag after reading the maintenance file and confirming the gap)

**HYGIENE** — missing something that should be there:
- Non-trivial feature with no test file
- `await` without try/catch in payment, auth, or DB paths

**GOOD_TO_HAVE** — minor nudge, not blocking:
- Missing rate limiting on public endpoints
- Missing input validation on user-facing forms

**DROP** (never report): large files, console.log unless leaking secrets, naming style, variable naming, anything already in existing findings, cross-file gaps you haven't confirmed by reading the other file.

Finding format (append to `.vibecheck/findings.json`):
```json
{"id":"vg-NNN","severity":"CRITICAL|PITFALL|HYGIENE|GOOD_TO_HAVE","title":"under 100 chars","file":"relative/path:line","why":"concrete consequence, under 200 chars","fix_prompt":"paste-ready fix","status":"open","source":"live","detected_at":"ISO timestamp"}
```
Max 3 new findings per response. Zero is valid. Never include secret values.

---

### Dev Tips

After reviewing for findings, scan for these patterns. State the consequence directly — one sentence, no hedging:

- **No tests for new feature** → "No tests here — if this breaks in prod, you'll be debugging blind."
- **New endpoint not wired to any caller** → "This endpoint exists but nothing calls it yet — dead code waiting to happen."
- **Big change touching 5+ files** → "This touches N files in one go — hard to review, harder to roll back."
- **Duplicate logic exists elsewhere** → "Similar logic already exists in [file] — two copies means two places to fix bugs."
- **No git commit, large change** → "Commit now. One crash and this is gone."
- **Changed behavior without updating callers** → "This changes existing behavior — callers not updated will break silently."
- **Approach that's hard to debug in production** → "Simple to write, complex to operate — think about how you'll debug this at 2am."
- **Schema change with no migration** → "Schema changed but no migration file — this fails in every environment that's not yours."

Max 2 tips per response. Skip if not genuinely applicable.

---

### Footer Format

**Verdict decision rule** (holistic judgment — worst finding wins):
- Any CRITICAL finding → `❌ Fix before shipping`
- Any PITFALL finding, no CRITICAL → `⚠️ OK for MVP, not prod`
- HYGIENE / GOOD_TO_HAVE only, or no findings → `✅ Safe to continue`

**Format** — write this at the very end of your response:
```
---
VibeCheck: [verdict]  [· 🔴 N critical · ⚡ N pitfalls · 🧹 N hygiene — omit zero categories]
🧪 Before shipping: [specific thing to verify — always show for non-trivial changes, skip only for trivial edits like comment fixes]
💡 [dev tip — one sentence, consequence-first — skip if nothing genuinely applies]
```

The `🧪` line must be specific to what was just built. Not "add tests" — name the exact flow, edge case, or command to run. Example: "run `/vibecheck-uninstall` and verify no command files remain" or "test the webhook endpoint with a forged signature header."

Commands: `/vibecheck` · `/vibecheck-detail <id>` · `/vibecheck-resolve <id>` · `/vibecheck-status`
