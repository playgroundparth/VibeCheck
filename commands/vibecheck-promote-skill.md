Run this bash command:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import sys, shutil
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project, store

args = '$ARGUMENTS'.strip().split()
if not args:
    print('Usage: /vibecheck-promote-skill <name>')
    print('       /vibecheck-skills  to list proposed skills')
    sys.exit(0)

name = args[0].removesuffix('.md')

cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

src = cwd / '.vibecheck' / 'proposed_skills' / f'{name}.md'
if not src.exists():
    available = [p.stem for p in (cwd / '.vibecheck' / 'proposed_skills').glob('*.md')] if (cwd / '.vibecheck' / 'proposed_skills').exists() else []
    if available:
        print(f'Skill \"{name}\" not found. Available: {available}')
    else:
        print('No proposed skills. Run /vibecheck-skills to check.')
    sys.exit(0)

# Strip 'PROPOSED — ' from description in frontmatter before promoting
content = src.read_text()
content = content.replace('PROPOSED — ', '')
content = content.replace('status: proposed', 'status: active')

dst_dir = Path('$ROOT') / '.claude' / 'skills'
dst_dir.mkdir(parents=True, exist_ok=True)
dst = dst_dir / f'{name}.md'

if dst.exists():
    print(f'Skill \"{name}\" is already active in .claude/skills/.')
    sys.exit(0)

dst.write_text(content)
store.log_event(cwd, {'type': 'skill_promoted', 'name': name, 'src': str(src), 'dst': str(dst)})

print(f'✅ Skill \"{name}\" promoted to .claude/skills/{name}.md')
print()
print('Claude will use this skill from the next session.')
print('To undo: delete .claude/skills/{name}.md')
"
```
