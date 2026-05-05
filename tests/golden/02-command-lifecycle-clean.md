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

## What Must NOT Happen

- Must not produce any PITFALL or CRITICAL finding
- Must not flag uninstall.js as a gap — foo.md is present
- Must not produce a finding just because it noticed the command is new
- The `🧪` line must be specific to the command change, not generic ("add tests")
