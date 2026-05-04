Run this bash command and display the output:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project

cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

skills_dir = cwd / '.vibecheck' / 'proposed_skills'
if not skills_dir.exists() or not list(skills_dir.glob('*.md')):
    print('[VibeCheck] No proposed skills.')
    print()
    print('Skills are auto-proposed when VibeCheck spots a project convention used 3+ times.')
    print('Use /vibecheck-promote-skill <name> to activate one.')
    sys.exit(0)

skills = sorted(skills_dir.glob('*.md'))
print(f'[VibeCheck] {len(skills)} proposed skill(s)\n')

for path in skills:
    content = path.read_text()
    lines = content.splitlines()
    name = path.stem
    desc = ''
    proposed_at = ''
    evidence = ''
    in_frontmatter = False
    for i, line in enumerate(lines):
        if line.strip() == '---':
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            if line.startswith('description:'):
                desc = line.split(':', 1)[1].strip().lstrip('PROPOSED —').strip()
            elif line.startswith('proposed_at:'):
                proposed_at = line.split(':', 1)[1].strip()[:10]
            elif line.startswith('evidence_files:'):
                evidence = line.split(':', 1)[1].strip()

    print(f'  {name}')
    if desc:
        print(f'    {desc}')
    if proposed_at:
        print(f'    Proposed: {proposed_at}')
    if evidence:
        print(f'    Evidence: {evidence}')
    print()

print('To activate a skill: /vibecheck-promote-skill <name>')
print('To view a skill:     Read .vibecheck/proposed_skills/<name>.md')
"
```
