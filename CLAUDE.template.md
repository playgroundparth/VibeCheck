# Project

## Context Capture — MANDATORY triggers

You MUST append to `.vibeguard/context_log.jsonl` BEFORE responding when ANY of these happen:

1. **Error resolved** — you fixed a bug or unblocked something that was failing
2. **Architecture/design decision** — a non-obvious choice was made (why matters, not just what)
3. **User preference discovered** — user corrected your approach, style, or rejected something
4. **Significant task completed** — multi-step feature or refactor finished
5. **20+ tool calls without a store** — write a progress summary

Do this BEFORE the rest of your response. Not after. Not "I'll note that." Write it now.

Do NOT store: trivial details, build logs, git status, anything already in CLAUDE.md.

### Format — append one line to `.vibeguard/context_log.jsonl`:
```json
{"ts":"ISO-timestamp","type":"error-resolved|decision|preference|task-completed|progress","summary":"what happened and why it matters","importance":"high|critical"}
```

To append: Read the file first (or treat as empty if missing), then Write the full content with the new line added.

---

## VibeCheck (active) — runs after every code change

After ANY response where you used Write, Edit, or MultiEdit tools, do this at the END of your response — after completing the user's request:

1. Read `.vibeguard/findings.json` to get existing findings and next ID
2. Read each file you just modified (you know which ones — you edited them this turn)
3. Check for security issues AND dev tips (rules below)
4. Write new security findings to `.vibeguard/findings.json`
5. Auto-resolve: for each open finding whose file you read, if issue is gone → set `status:"resolved"`, add `resolved_at`, `resolution_note:"auto-resolved"`
6. **Always end your response with a VibeCheck footer** (format below)

---

### Security Rules

**CRITICAL** — flag only if you can state a concrete exploit:
- Route handles user data without auth check
- User input in DB query (SQL injection)
- User-controlled path in file read/write (path traversal)
- Webhook/payment endpoint without signature verification
- API response leaks data the caller shouldn't see
- Secret/credential hardcoded in source

**PITFALL** — architectural trap, not immediately exploitable:
- In-memory rate limiting or counters (won't survive restarts)
- Custom auth/JWT instead of using a library
- New feature built on top of code that is already broken

**HYGIENE**:
- Non-trivial feature with no test file
- `await` without try/catch in payment, auth, or DB paths

**GOOD_TO_HAVE** — minor only, never for praise:
- Missing rate limiting on public endpoints
- Missing input validation on user-facing forms

**DROP** (never report): large files, console.log unless leaking secrets, naming style, anything already in existing findings.

Finding format (append to `.vibeguard/findings.json`):
```json
{"id":"vg-NNN","severity":"CRITICAL|PITFALL|HYGIENE|GOOD_TO_HAVE","title":"under 100 chars","file":"relative/path:line","why":"concrete consequence, under 200 chars","fix_prompt":"paste-ready fix","status":"open","source":"live","detected_at":"ISO timestamp"}
```
Max 3 new security findings. Zero is valid. Never include secret values.

---

### Dev Tips (show these prominently, not buried)

After the security check, scan for these patterns and call them out. Be a senior dev giving real advice — direct, confident, and specific. State the consequence clearly. Wit is a bonus, not the point. Never ask a question when you should make a statement.

Look for:
- **No tests written for new feature** → "No tests here — if this breaks in prod, you'll be debugging blind. Add at least a smoke test."
- **New API route/endpoint not wired to any UI** → "This endpoint exists but nothing calls it yet. Wire it up or it's dead code waiting to happen."
- **Big change touching 5+ files** → "This touches N files in one go — hard to review, harder to roll back. Ship phase 1, validate, then continue."
- **Duplicate logic already exists elsewhere** → "Similar logic already exists in [file]. Keeping two copies means two places to fix bugs."
- **No git commit in a while (large change)** → "Commit your work now. One crash and this is gone — no undo for unsaved progress."
- **Missing backward compat check** → "This changes existing behavior. Any callers not updated will break silently."
- **Approach will cause ops complexity** → "This is simple to write but complex to operate — think about how you'll debug it at 2am."
- **Backend/DB change with no migration** → "Schema changed but no migration file. This will fail in every environment that's not yours."

Keep each tip to ONE direct sentence (two max if the consequence needs context). Max 2 tips per response. Skip if genuinely not applicable — don't force it.

---

### Footer Format

Write this at the very end of your response.

**If security issues found:**
```
---
VibeCheck: 🔴 N critical · ⚡ N pitfalls · 🧹 N hygiene
💡 [dev tip — direct, one sentence, consequence-first]
```

**If clean:**
```
---
VibeCheck: ✅ [short clean-bill line — honest, not hype. Vary it: "All clear." / "Nothing flagged." / "No issues." / one dry quip max]
💡 [dev tip if genuinely applicable — skip if not]
```

Don't oversell the clean state. Don't force a quip. One dry line is fine; silence on the joke is better than a forced reference.

Commands: `/vibecheck` · `/vibecheck-detail <id>` · `/vibecheck-resolve <id>` · `/vibecheck-status`
