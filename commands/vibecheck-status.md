Run this bash command and display the output:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project, store

cwd = project.find_project_root(Path('$ROOT'))
if not cwd or not store.is_initialized(cwd):
    print('VibeCheck not initialized in this project.')
    sys.exit(0)

findings_path = cwd / '.vibecheck' / 'findings.json'
findings = json.loads(findings_path.read_text()) if findings_path.exists() else []
if isinstance(findings, dict): findings = findings.get('findings', [])

open_f = [f for f in findings if f.get('status', 'open') not in ('resolved', 'dismissed')]
by_sev = {}
for f in open_f:
    s = f.get('severity', 'UNKNOWN')
    by_sev[s] = by_sev.get(s, 0) + 1

icons = {'CRITICAL': '🔴', 'PITFALL': '⚡', 'HYGIENE': '🧹', 'GOOD_TO_HAVE': '💡'}
order = ['CRITICAL', 'PITFALL', 'HYGIENE', 'GOOD_TO_HAVE']
parts = [f\"{icons[s]} {by_sev[s]} {s.lower().replace('_',' ')}\" for s in order if s in by_sev]
summary = ' · '.join(parts) if parts else 'no open findings'
print(f'[VibeCheck] {summary}')
print('Commands: /vibecheck · /vibecheck-detail · /vibecheck-resolve · /vibecheck-report · /vibecheck-scan')
"
```
