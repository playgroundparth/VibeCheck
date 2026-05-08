Run this bash command and display the output:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project

MODELS = {
    'haiku':  {'id': 'claude-haiku-4-5-20251001',  'label': 'Claude Haiku 4.5',  'note': 'fast · cheapest · good for most projects'},
    'sonnet': {'id': 'claude-sonnet-4-6',           'label': 'Claude Sonnet 4.6', 'note': 'deeper analysis · ~5x cost'},
}

arg = '$ARGUMENTS'.strip().lower()

cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

config_path = cwd / '.vibecheck' / 'config.json'
config = json.loads(config_path.read_text()) if config_path.exists() else {}
current = config.get('model', 'haiku')

if not arg:
    print('[VibeCheck] Analyzer model\n')
    for key, m in MODELS.items():
        marker = ' ◀ current' if key == current else ''
        print(f'  {key:8}  {m[\"label\"]:30} {m[\"note\"]}{marker}')
    print()
    print('Switch with: /vibecheck-model haiku  or  /vibecheck-model sonnet')
    sys.exit(0)

if arg not in MODELS:
    print(f'Unknown model \"{arg}\". Choose: haiku, sonnet')
    sys.exit(1)

if arg == current:
    print(f'Already using {MODELS[arg][\"label\"]}.')
    sys.exit(0)

config['model'] = arg
config_path.write_text(json.dumps(config, indent=2))
print(f'✅ Switched to {MODELS[arg][\"label\"]} ({MODELS[arg][\"note\"]})')
print()
print('The /vibecheck-scan command will use this model on the next run.')
"
```
