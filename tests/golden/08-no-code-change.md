# Golden: No Code Change → Minimal Output, No Findings

## Scenario

Developer updates the README. No source files were modified. No security surface changed. No logic was touched.

## What Changed

```
README.md   ← updated (prose edits, no code examples changed)
```

## Evidence Files VibeCheck Should Read

```
README.md   ← the changed file
```

No `project_map.json` group matches README. No lifecycle check triggered. No artifact group relationships to verify.

## Evidence Found

`README.md` contains prose. No credentials, no configuration, no hardcoded values that weren't there before. The change is documentation.

## Expected VibeCheck Output

**Findings:** none

**Footer:**
```
---
VibeCheck: ✅ Safe to continue
```

No `🧪` line. No `💡` tip. The output is minimal because there is nothing to say.

Acceptable variants:
```
---
VibeCheck: ✅ Nothing flagged.
```
```
---
VibeCheck: ✅ All clear.
```

## Global Invariant

- **verdict is present** — ✅ Safe to continue
- **verdict answers "can I continue?"** — yes, immediately

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce any finding — README changes have no security surface
- ❌ Must not produce ⚠️ or ❌ for a documentation change

**Over-triggering:**
- ❌ Must not invent a finding about "missing test documentation"
- ❌ Must not flag "no tests for this change" — README doesn't need tests
- ❌ Must not flag missing rate limiting, auth checks, or any security rule — none apply
- ❌ Must not run the full 8-step cross-file analysis for a README-only change
- ❌ Must not produce a `🧪` line — there is nothing to verify before shipping a README edit

**Bloat:**
- ❌ Must not produce a lengthy response praising the documentation
- ❌ Must not produce a `💡` tip that isn't directly relevant to the README change
- ❌ "Great work keeping the README updated" — VibeCheck is not a cheerleader

**The key behavior this golden enforces:**
- VibeCheck fires after every response with Write/Edit tool use, including README edits
- For non-code changes, the correct behavior is minimal output and exit fast
- Silence is a valid and correct answer when there is genuinely nothing to say
