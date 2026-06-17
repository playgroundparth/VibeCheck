Run this bash command to display quick reference help:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/lib/vc_display.py" "help"
```
