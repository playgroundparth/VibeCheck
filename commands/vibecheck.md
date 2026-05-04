Run this bash command and display the output exactly as-is, without reformatting or summarizing:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/lib/vg_display.py"
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import sys; sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import telemetry, project
from pathlib import Path
cwd = project.find_project_root(Path('$ROOT'))
if cwd:
    cfg = telemetry.load_config(cwd)
    telemetry.track_vibecheck_invoked(cfg)
" 2>/dev/null &
```

Do not rewrite, reorder, or add to the output. Display it verbatim.
