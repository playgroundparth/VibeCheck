# Golden: Command Lifecycle Clean → No Finding

## Scenario

Developer adds a new slash command file. All three lifecycle scripts (init, update, uninstall) include it. No drift.

## What Changed

```
commands/foo.md   ← new file
```

## Evidence Files VibeCheck Should Read

From `project_map.json` → `slash_commands` group → `must_check`:

```
bin/init.js
bin/update.js
bin/uninstall.js
```

## Evidence Found

`bin/init.js`:
```js
const commandFiles = ["bar.md", "baz.md", "foo.md"];  // ✅
```

`bin/update.js`:
```js
const commandFiles = ["bar.md", "baz.md", "foo.md"];  // ✅
```

`bin/uninstall.js`:
```js
const commandFiles = ["bar.md", "baz.md", "foo.md"];  // ✅
```

## Expected VibeCheck Output

**Findings:** none (0 findings)

**Footer:**
```
---
VibeCheck: ✅ Safe to continue
🧪 Before shipping: test that the command works end-to-end after a fresh install
```

## Global Invariant

- **verdict is present** — ✅ Safe to continue
- **verdict answers "can I continue?"** — yes

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce any PITFALL or CRITICAL finding — all lifecycle scripts are consistent
- ❌ Must not produce ⚠️ just because a new file was added

**Generic output:**
- ❌ "Consider adding tests for the new command" — not applicable to a markdown file
- ❌ "You may want to verify lifecycle coverage" — VibeCheck verified it; the answer is clean
- ❌ Findings that weren't derived from reading the evidence files
- ❌ `🧪` line that says "add tests" — specific to the install/uninstall flow instead

**Wrong scope:**
- ❌ Must not flag README as missing — nice_check is only reported when must_check is clean, and only if the gap is real
- ❌ Must not manufacture a finding to seem thorough
