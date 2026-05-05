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

If the check above fails, stop here.

## Choose scanner based on arguments

Parse `$ARGUMENTS`:

**`--deep`** → invoke SubAgent `vibecheck-scanner-deep` (Sonnet model, reads up to 35 files, up to 20 findings). Use when you want thorough analysis, are scanning a large or security-critical codebase, or the standard scan missed something you expected to catch.

**`--quick`** or empty → invoke SubAgent `vibecheck-scanner` (Haiku model, reads up to 20 files, up to 15 findings). Fast and cheap (~$0.02). Good for a first scan or after a batch of changes.

**Anything else** (e.g. `auth`, `src/queue`, `payments`) → invoke SubAgent `vibecheck-scanner` but include the argument as a focus instruction in the SubAgent prompt:
> "Focus this scan specifically on: [argument]. In Phase 2, prioritize reading files related to that area. You may still read a broader file or two for project context, but spend most of your file budget on the focus area."

## After the scan

Read `<project-root>/.vibecheck/findings.json` and show a summary grouped by severity using the same format as `/vibecheck`.
