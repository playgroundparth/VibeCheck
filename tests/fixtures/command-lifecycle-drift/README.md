# Fixture: command-lifecycle-drift

## Scenario

`commands/foo.md` was just added to the project.

`bin/init.js` and `bin/update.js` include it in their copy lists (correct).
`bin/uninstall.js` does NOT include it (the bug — lifecycle drift).

## What the artifact group says

`project_map.artifact_groups.slash_commands` declares:
- `installed_by`: `[bin/init.js, bin/update.js]`
- `removed_by`: `[bin/uninstall.js]`
- `must_check`: `[installed_by, removed_by]` → gaps here are **PITFALL**
- `nice_check`: `[documented_in]` → gaps here are **HYGIENE**

## What must happen

**Deterministic (Python layer — asserted in tests/test_project_map.py):**
- `find_artifact_group("commands/foo.md", groups)` → `("slash_commands", group)`
- `lifecycle_files_for_changed(cwd, [commands/foo.md])` → must_check includes `bin/uninstall.js`
- `severity_for_missing_relationship(group, "removed_by")` → `"PITFALL"`
- `severity_for_missing_relationship(group, "documented_in")` → `"HYGIENE"` or `"GOOD_TO_HAVE"`

**LLM review (golden contract — see expected/finding.json):**
- Reads `bin/uninstall.js` as a must-check file
- Finds `foo.md` absent from the commandFiles array
- Creates a **PITFALL** finding pointing to `bin/uninstall.js`
- Verdict: `⚠️ OK for MVP, not prod`
- `🧪 Before shipping:` mentions running uninstall and checking for foo.md

## What must NOT happen

- The finding must not be CRITICAL (no exploit, no crash)
- The finding must not be downgraded to HYGIENE (it's in must_check)
- The fixture must not produce a finding if uninstall.js is also fixed (see command-lifecycle-clean)
