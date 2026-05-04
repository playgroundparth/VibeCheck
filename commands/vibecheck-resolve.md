Run this bash command:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import json, sys, datetime
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project

args = '$ARGUMENTS'.strip().split(None, 1)
if not args or not args[0]:
    print('Usage: /vibecheck-resolve <id> [note]  e.g. /vibecheck-resolve vg-001 fixed')
    sys.exit(0)

fid = args[0]
note = args[1] if len(args) > 1 else ''

cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

findings_path = cwd / '.vibecheck' / 'findings.json'
findings = json.loads(findings_path.read_text())
if isinstance(findings, dict): findings = findings.get('findings', [])

f = next((x for x in findings if x.get('id') == fid), None)
if not f:
    ids = [x.get('id') for x in findings]
    print(f'Finding {fid} not found. Available: {ids}')
    sys.exit(0)

f['status'] = 'resolved'
f['resolved_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
if note: f['resolution_note'] = note

findings_path.write_text(json.dumps(findings, indent=2))
print(f'✅ {fid} marked as resolved.')
if note: print(f'   Note: {note}')

import telemetry
cfg = telemetry.load_config(cwd)
telemetry.track_finding_resolved(cfg, was_dismissed=False)
"
```
