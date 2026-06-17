Run this bash command and display the output exactly as-is, without reformatting or summarizing:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/lib/vc_display.py" "$ARGUMENTS"
```

Display the output above verbatim — do not rewrite or reorder it.

After displaying the output, if no arguments were passed, or if the argument is `report`, use `mcp__Claude_Preview__preview_start` with `name: "vibecheck-report"` to open the full HTML report in the side panel. This shows all findings with complete fix prompts.
