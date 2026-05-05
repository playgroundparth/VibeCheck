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

**Finding:**
```json
{
  "severity": "PITFALL",
  "title": "commands/foo.md is installed but not removed by uninstall.js",
  "file": "bin/uninstall.js",
  "why": "foo.md will persist in .claude/commands/ after uninstall — stale command stays active"
}
```

**Footer:**
```
---
VibeCheck: ⚠️ OK for MVP, not prod · ⚡ 1 pitfall
🧪 Before shipping: run uninstall and verify .claude/commands/foo.md is gone
💡 uninstall.js commandFiles is out of sync — every new command needs to be added to all three lifecycle scripts
```

## What Must NOT Happen

- Must not produce CRITICAL
- Must not produce ✅ Safe to continue
- Must not flag README or documentation as missing (nice_check gaps are not shown when must_check gaps exist)
- Must not flag if it only read `commands/foo.md` and not the lifecycle scripts
