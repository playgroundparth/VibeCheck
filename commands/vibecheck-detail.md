Run this bash command and display the formatted output:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project

fid = '$ARGUMENTS'.strip()
if not fid:
    print('Usage: /vibecheck-detail <id>  e.g. /vibecheck-detail vg-001')
    sys.exit(0)

cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

findings = json.loads((cwd / '.vibecheck' / 'findings.json').read_text())
if isinstance(findings, dict): findings = findings.get('findings', [])

f = next((x for x in findings if x.get('id') == fid), None)
if not f:
    ids = [x.get('id') for x in findings]
    print(f'Finding {fid} not found. Available: {ids}')
    sys.exit(0)

icon = {'CRITICAL':'🔴','PITFALL':'⚡','HYGIENE':'🧹','GOOD_TO_HAVE':'💡'}.get(f.get('severity',''), '•')
print(f\"{f['id']} {icon} {f.get('severity','')} — {f.get('title','')}\")
if f.get('file'): print(f\"File: {f['file']}\")
print()
if f.get('why'): print(f\"Why it matters:\n{f['why']}\n\")
if f.get('details'): print(f\"Detail:\n{f['details']}\n\")
if f.get('fix_prompt'): print(f\"Fix — paste to Claude:\n{f['fix_prompt']}\n\")
print(f\"Status: {f.get('status','open')} | Source: {f.get('source','')} | Detected: {f.get('detected_at','')[:10]}\")
print(f\"\nResolve with: /vibecheck-resolve {fid}\")
"
```
