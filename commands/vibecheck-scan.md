Run a VibeCheck full-repo scan using the vibecheck-scanner agent.

First confirm VibeCheck is initialized:
```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import sys; from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project, store
cwd = project.find_project_root(Path('$ROOT'))
print('project:', cwd)
print('initialized:', store.is_initialized(cwd) if cwd else False)
"
```

Then invoke the SubAgent tool with agent `vibecheck-scanner` to run the full scan.

After the scan completes, read `<project-root>/.vibecheck/findings.json` and show a summary grouped by severity.
