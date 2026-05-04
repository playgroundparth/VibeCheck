Run this bash command and display the output:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project

cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

tl = cwd / '.vibecheck' / 'timeline.json'
if not tl.exists():
    print('No timeline yet — run some tasks first.')
    sys.exit(0)

events = json.loads(tl.read_text())
if isinstance(events, dict):
    events = events.get('events', [])

limit = int('$ARGUMENTS'.strip()) if '$ARGUMENTS'.strip().isdigit() else 20
events = events[-limit:]

icons = {
    'task_completed': '✏️',
    'analysis_run': '🔍',
    'finding_added': '⚠️',
    'finding_resolved': '✅',
    'finding_dismissed': '🗑️',
    'pattern_created': '📐',
    'pattern_promoted': '📈',
    'pattern_demoted': '📉',
    'pattern_killed': '💀',
    'skill_promoted': '⭐',
    'session_start': '▶️',
}

if not events:
    print('Timeline is empty.')
    sys.exit(0)

print(f'[VibeCheck] Last {len(events)} events\n')
for e in reversed(events):
    ts = e.get('ts', '')[:16].replace('T', ' ')
    etype = e.get('type', 'unknown')
    icon = icons.get(etype, '·')
    detail = ''
    if etype == 'task_completed':
        n = e.get('file_count', 0)
        detail = f\"{n} file{'s' if n != 1 else ''} changed\"
    elif etype == 'analysis_run':
        detail = f\"{e.get('files_analyzed', 0)} files · {e.get('findings_added', 0)} findings\"
    elif etype in ('finding_added', 'finding_resolved', 'finding_dismissed'):
        detail = e.get('finding_id', '') + (f\" — {e.get('title', '')[:50]}\" if e.get('title') else '')
    elif etype in ('pattern_created', 'pattern_promoted', 'pattern_demoted', 'pattern_killed'):
        detail = e.get('name', '') + (f\" → {e.get('to', '')}\" if e.get('to') else '') + (f\" ({e.get('reason', '')})\" if e.get('reason') else '')
    elif etype == 'session_start':
        detail = e.get('open_findings', '')
    print(f'  {ts}  {icon} {etype.replace(\"_\", \" \")}  {detail}')
"
```
