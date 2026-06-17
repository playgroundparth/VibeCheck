# VibeCheck

VibeCheck is active in this project. It runs security analysis inline at the end of every response where files were changed.

## Commands

- `/vibecheck` — Central console (dashboard, details, resolve, report, timeline, stage/mode configs)
- `/vibecheck-scan` — One-time repository scan
- `/vibecheck-review` — Review current git diff for flaws
- `/vibecheck-skills` — List and promote integration context skills
- `/vibecheck-help` — Quick reference guide

## Findings are in `.vibecheck/findings.json`

Severity levels: CRITICAL · PITFALL · HYGIENE · GOOD_TO_HAVE

The analysis runs inline — no background process, no extra cost. See CLAUDE.md for the full rules Claude follows.
