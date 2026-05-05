Run this bash command and display the output exactly as-is, without reformatting or summarizing:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project, store

fid = '$ARGUMENTS'.strip()
cwd = project.find_project_root(Path('$ROOT'))
if not cwd or not store.is_initialized(cwd):
    print('VibeCheck not initialized. Run: npx github:playgroundparth/VibeCheck init')
    sys.exit(0)

findings_path = cwd / '.vibecheck' / 'findings.json'
if not findings_path.exists():
    print('No findings yet. Try \`/vibecheck-scan\` to run a full scan.')
    sys.exit(0)

all_findings = json.loads(findings_path.read_text())
if isinstance(all_findings, dict): all_findings = all_findings.get('findings', [])

# Detail view for a specific finding
if fid:
    f = next((x for x in all_findings if x.get('id') == fid), None)
    if not f:
        ids = [x.get('id') for x in all_findings if x.get('status','open') == 'open']
        print(f'Finding {fid} not found. Open findings: {ids}')
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
    sys.exit(0)
" 2>/dev/null
# Summary view (no ID passed)
if [ -z "$ARGUMENTS" ]; then
  PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/lib/vg_display.py"
fi
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
