Run a VibeCheck scan of this codebase.

Arguments: $ARGUMENTS

First confirm VibeCheck is initialized:
```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import sys; from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project, store
cwd = project.find_project_root(Path('$ROOT'))
if not cwd or not store.is_initialized(cwd):
    print('VibeCheck not initialized. Run: npx github:playgroundparth/VibeCheck init')
    sys.exit(1)
print('project:', cwd)
" 2>&1
```

If the initialization check fails, stop here.

## Parse arguments and choose scanner

Arguments to parse from: `$ARGUMENTS`

**Model selection** (pick one; defaults to haiku):
- `--model haiku` → `vibecheck-scanner` (fast, ~$0.02)
- `--model sonnet` or `--deep` → `vibecheck-scanner-deep` (thorough, ~$0.20)
- `--model opus` → `vibecheck-scanner-opus` (exhaustive, ~$1–2)

**File budget** (optional; pass as an instruction to the agent):
- `--files N` → tell the agent: "Read up to N files total (overrides default)."
- `--full` → tell the agent: "Read all source files you can find in priority order. Use find to list everything, then read in order: entry points, auth, routes, DB, config, tests."

**Focus area** (optional; any non-flag argument):
- `auth`, `payments`, `src/queue`, etc. → tell the agent: "Focus this scan on: [area]. Spend most of your file budget reading files related to that area."

Build the SubAgent prompt from the above. Example: if user typed `/vibecheck-scan --model sonnet --files 50 auth`, invoke `vibecheck-scanner-deep` with the prompt: "Focus on: auth. Read up to 50 files total (overrides default 35)."

If no model flag: use `vibecheck-scanner` (haiku).
If no file flag: use the agent's default.
If no focus: no focus instruction needed.

## After the scan

Read `<project-root>/.vibecheck/findings.json` and show a summary grouped by severity — same format as `/vibecheck`.

## Quick reference

| Command | Model | Files | Use when |
|---|---|---|---|
| `/vibecheck-scan` | Haiku | 20 | First scan, quick check, ~$0.02 |
| `/vibecheck-scan --deep` | Sonnet | 35 | Thorough review, ~$0.20 |
| `/vibecheck-scan --model opus` | Opus | 50 | Maximum depth, ~$1–2 |
| `/vibecheck-scan --model sonnet --files 50` | Sonnet | 50 | Deep + wider coverage |
| `/vibecheck-scan --full` | Haiku | All | Read every source file |
| `/vibecheck-scan --model opus --full` | Opus | All | Exhaustive, no sampling |
| `/vibecheck-scan auth` | Haiku | 20 | Focused on auth/session files |
| `/vibecheck-scan --model sonnet payments` | Sonnet | 35 | Deep focus on payments |
