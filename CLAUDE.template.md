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

**Installer/uninstaller rule**: if a file is added to an installed, generated, or copied set (commands, hooks, lib files, routes, plugins), read both the installer path AND the uninstaller/cleanup path. This is the check that catches "you added the file but forgot to clean it up on uninstall."

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

**CRITICAL** — concrete exploit OR code that will definitely crash or corrupt data in production:
- Route handles user data without auth check
- User input in DB query (SQL injection)
- User-controlled path in file read/write (path traversal)
- Webhook/payment endpoint without signature verification
- API response leaks data the caller shouldn't see
- Secret/credential hardcoded in source
- Logic that will definitely crash or corrupt (wrong condition on write, missing null check on field that will be null)

**PITFALL** — works today, causes pain later:
- OVERBUILDING — complexity that exceeds what this stage needs (caching before load, premature abstraction)
- REINVENTING — building something that already exists and works better (custom JWT, custom email, custom queues)
- WRONG ABSTRACTION — structure that will resist the next obvious change
- In-memory state that won't survive restarts
- Cross-file inconsistency — confirmed after reading the maintenance file

**HYGIENE** — missing something that should be there:
- Non-trivial feature with no test file
- `await` without try/catch in payment, auth, or DB paths

**GOOD_TO_HAVE** — minor nudge, not blocking:
- Missing rate limiting on public endpoints
- Missing input validation on user-facing forms

**DROP**: large files, console.log unless leaking secrets, naming style, anything already in existing findings, cross-file gaps you haven't confirmed by reading the other file.

Finding format (append to `.vibecheck/findings.json`):
```json
{"id":"vg-NNN","severity":"CRITICAL|PITFALL|HYGIENE|GOOD_TO_HAVE","title":"under 100 chars","file":"relative/path:line","why":"concrete consequence, under 200 chars","fix_prompt":"paste-ready fix","status":"open","source":"live","detected_at":"ISO timestamp"}
```
Max 3 new findings. Zero is valid. Never include secret values.

Auto-resolve: for each open finding whose file you read, if issue is gone → set `status:"resolved"`, add `resolved_at`, `resolution_note:"auto-resolved"`.

---

### Step 7 — Update memory and project_map

If you discovered a new project convention this turn:
- Append to `memory.json` → `known_conventions` array
- If it's a new artifact group relationship, add it to `project_map.json` → `artifact_groups`

If you caught a gap that matches a prior miss pattern:
- Append to `memory.json` → `recent_misses` with what was found and when

Write the updated file (Read first, merge, Write back).

---

### Step 8 — Dev tip + verdict

After the security/correctness check, scan for:
- No tests for new feature → "No tests here — if this breaks in prod, you'll be debugging blind."
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

Commands: `/vibecheck` · `/vibecheck-detail <id>` · `/vibecheck-resolve <id>` · `/vibecheck-status`
