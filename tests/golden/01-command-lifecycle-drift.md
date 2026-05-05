# Golden: Command Lifecycle Drift → PITFALL

## Scenario

Developer adds a new slash command file. The installer picks it up. The uninstaller doesn't.

## What Changed

```
commands/foo.md   ← new file (the change that triggers review)
```

## Evidence Files VibeCheck Should Read

From `project_map.json` → `slash_commands` group → `must_check`:

```
bin/init.js       ← installed_by
bin/update.js     ← updated_by
bin/uninstall.js  ← removed_by  ← THE GAP IS HERE
```

## Evidence Found

`bin/init.js`:
```js
const commandFiles = ["bar.md", "baz.md", "foo.md"];  // ✅ foo.md present
```

`bin/uninstall.js`:
```js
const commandFiles = ["bar.md", "baz.md"];  // ❌ foo.md missing
```

## Expected VibeCheck Output

**Finding (evidence-anchored):**
```json
{
  "severity": "PITFALL",
  "title": "commands/foo.md is installed but not removed by uninstall.js",
  "file": "bin/uninstall.js:2",
  "files_read": ["commands/foo.md", "bin/init.js", "bin/uninstall.js"],
  "why": "foo.md will persist in .claude/commands/ after uninstall — stale command stays active"
}
```

**Footer:**
```
---
VibeCheck: ⚠️ OK for MVP, not prod · ⚡ 1 pitfall
🧪 Before shipping: run uninstall and verify .claude/commands/foo.md is gone
💡 uninstall.js commandFiles is out of sync — every new command needs to be in all three lifecycle scripts
```

## Global Invariant

- **verdict is present** — ⚠️ OK for MVP, not prod
- **verdict answers "can I continue?"** — yes, but fix before prod

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce ❌ Fix before shipping — no concrete exploit
- ❌ Must not produce ✅ Safe to continue — there is a real gap

**Generic output:**
- ❌ "Consider updating uninstall.js" — state the consequence, not the suggestion
- ❌ "You may want to check lifecycle scripts" — VibeCheck checked them; name the gap
- ❌ Finding with no `file:line` reference
- ❌ Finding that doesn't name which files were read (`files_read` missing)

**Wrong scope:**
- ❌ Must not flag README or documentation as missing — nice_check gaps are suppressed when must_check gaps exist
- ❌ Must not produce a finding without having actually read `bin/uninstall.js`
- ❌ `🧪` line must name the specific file (`foo.md`), not say "test the uninstall flow"
