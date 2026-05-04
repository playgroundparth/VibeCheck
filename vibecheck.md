# VibeCheck

VibeCheck is active in this project. It runs security analysis inline at the end of every response where files were changed.

## Commands

- `/vibecheck` — show open findings with fix prompts
- `/vibecheck-detail <id>` — full detail on one finding
- `/vibecheck-resolve <id>` — mark a finding as resolved
- `/vibecheck-scan` — one-time scan of the full codebase
- `/vibecheck-status` — health metrics

## Findings are in `.vibeguard/findings.json`

Severity levels: CRITICAL · PITFALL · HYGIENE · GOOD_TO_HAVE

The analysis runs inline — no background process, no extra cost. See CLAUDE.md for the full rules Claude follows.
