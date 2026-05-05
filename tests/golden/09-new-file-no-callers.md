# Golden: New File, No Callers → PITFALL (DEAD_ON_ARRIVAL)

## Scenario

Developer creates a new utility module. It has useful exports. But no other file in the project imports it — not yet, maybe not ever.

## What Changed

```
lib/formatter.py   ← new file
```

## Evidence Files VibeCheck Should Read

```
lib/formatter.py   ← the changed file
```

Then: grep for `import formatter` across the project.

```
grep -r "import formatter\|from formatter" . --include="*.py"
(no results)
```

No match means no callers.

## Evidence Found

`lib/formatter.py`:
```python
def format_currency(amount: int, currency: str = "USD") -> str:
    """Format cents as a currency string."""
    return f"${amount / 100:.2f}"

def format_date(dt) -> str:
    return dt.strftime("%b %d, %Y")
```

`grep result`: zero matches for `import formatter` or `from formatter import` across the whole project.

## Expected VibeCheck Output

**Finding (evidence-anchored):**
```json
{
  "severity": "PITFALL",
  "title": "formatter.py added but nothing imports it",
  "file": "lib/formatter.py",
  "files_read": ["lib/formatter.py"],
  "why": "No callers found — this file ships as dead code unless something imports it"
}
```

**Footer:**
```
---
VibeCheck: ⚠️ OK for MVP, not prod · ⚡ 1 pitfall
🧪 Before shipping: import and call format_currency() from wherever it's actually needed
💡 Nothing imports this yet — wire it up now or you'll forget it exists
```

## Global Invariant

- **verdict is present** — ⚠️ OK for MVP, not prod
- **verdict answers "can I continue?"** — yes, but wire it up before shipping

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce ✅ — an orphaned module is real drag
- ❌ Must not produce ❌ — no security issue, no data loss

**Generic output:**
- ❌ Finding without actually running the grep — must confirm zero callers, not assume
- ❌ `files_read` missing the grep result — the finding is only valid if the search was run
- ❌ "Consider importing this module" — state the consequence (ships as dead code)
- ❌ Flagging the module's internal logic (correct formatting code is not the problem)

**Skip list (must NOT flag these even if no callers):**
- ❌ `index.py`, `__init__.py`, `main.py`, `app.py` — entry points, intentionally standalone
- ❌ `test_formatter.py` — test files are expected to only be called by the test runner
- ❌ `formatter.config.ts`, `jest.config.js` — config files

**Wrong scope:**
- ❌ Must not flag pre-existing files with no callers — only files created this turn
- ❌ Must not flag if the file IS imported elsewhere (grep returned results)
