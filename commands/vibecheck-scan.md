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

**Mode/Model selection** (pick one; defaults to the configured mode):
- `--lite`, or using a lite model (`haiku`, `gemini-flash`, `gpt-5.4-mini`) → `vibecheck-scanner` (fast, lowest cost)
- `--deep`, `--full`, or using a full model (`sonnet`, `gemini-pro`, `gpt-5.4`) → `vibecheck-scanner-deep` (thorough, balanced)
- `--pro`, or using a pro model (`opus`, `gpt-5.5`) → `vibecheck-scanner-opus` (exhaustive, deepest analysis)

**Scan mode** (optional):
- `--full` → tell the agent: "FULL REPO SCAN. Run all grep-first discovery sections (2a–2i plus 2j for each derived check) before reading any files. Read every file the greps return. Do not stop until all sections are complete."
- `--files N` → tell the agent: "Limit reads to N files total (overrides default)."

**Focus area** (optional; any non-flag argument):
- `auth`, `payments`, `src/queue`, etc. → tell the agent: "Focus this scan on: [area]. Weight grep sections toward that area — still run all greps but prioritize reading files from that domain."

Build the SubAgent prompt from the above. Example: if user typed `/vibecheck-scan --deep auth`, invoke `vibecheck-scanner-deep` with: "Focus on: auth."

If no mode or model flag: check configured mode (default is `full` -> `vibecheck-scanner-deep`).
If no scan mode flag: use agent defaults (grep-first applies to all modes).
If no focus: no focus instruction needed.

## After the scan

Run this and display the output exactly as-is:
```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/lib/vc_display.py" 2>/dev/null
```

Display the output verbatim — do not rewrite or summarize.

Then use `mcp__Claude_Preview__preview_start` with `name: "vibecheck-report"` to open the full HTML report in the side panel.

## Quick reference

| Command | Model | Coverage | Use when |
|---|---|---|---|
| `/vibecheck-scan` | Haiku | grep-identified files | First scan, quick check, ~$0.05 |
| `/vibecheck-scan --deep` | Sonnet | grep-identified files, deeper analysis | Thorough review, ~$0.30 |
| `/vibecheck-scan --model opus` | Opus | grep-identified files, exhaustive | Maximum depth, ~$2–4 |
| `/vibecheck-scan --full` | Haiku | all grep sections + derived checks | Full coverage, no sampling |
| `/vibecheck-scan --deep --full` | Sonnet | all grep sections + derived checks | Deep full coverage |
| `/vibecheck-scan auth` | Haiku | grep-identified, auth-weighted | Focused on auth/session files |
| `/vibecheck-scan --deep payments` | Sonnet | grep-identified, payments-weighted | Deep focus on payments |
