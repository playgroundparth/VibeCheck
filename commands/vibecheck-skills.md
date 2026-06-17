Run this bash command:

```bash
ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)
PYTHONPATH="$ROOT/.claude/hooks/lib" python3 -c "
import sys, shutil, os
from pathlib import Path
sys.path.insert(0, '$ROOT/.claude/hooks/lib')
import project, store

args = '$ARGUMENTS'.strip().split()
cwd = project.find_project_root(Path('$ROOT'))
if not cwd:
    print('VibeCheck not initialized.')
    sys.exit(0)

# Resolve app directory name from PYTHONPATH
pythonpath = os.environ.get('PYTHONPATH', '')
app_dir_name = '.claude'
for d in ('.claude', '.agents', '.codex'):
    if d in pythonpath:
        app_dir_name = d
        break

if len(args) > 0 and args[0].lower() == 'promote' and len(args) > 1:
    name = args[1].removesuffix('.md')
    src = cwd / '.vibecheck' / 'proposed_skills' / f'{name}.md'
    if not src.exists():
        available = [p.stem for p in (cwd / '.vibecheck' / 'proposed_skills').glob('*.md')] if (cwd / '.vibecheck' / 'proposed_skills').exists() else []
        if available:
            print(f'Skill \"{name}\" not found. Available: {available}')
        else:
            print('No proposed skills.')
        sys.exit(0)

    content = src.read_text()
    content = content.replace('PROPOSED — ', '')
    content = content.replace('status: proposed', 'status: active')

    dst_dir = cwd / app_dir_name / 'skills'
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f'{name}.md'

    if dst.exists():
        print(f'Skill \"{name}\" is already active in {app_dir_name}/skills/.')
        sys.exit(0)

    dst.write_text(content)
    store.log_event(cwd, {'type': 'skill_promoted', 'name': name, 'src': str(src), 'dst': str(dst)})

    print(f'✅ Skill \"{name}\" promoted to {app_dir_name}/skills/{name}.md')
    print()
    print('The client will use this skill from the next session.')
    print(f'To undo: delete {app_dir_name}/skills/{name}.md')
    sys.exit(0)

skills_dir = cwd / '.vibecheck' / 'proposed_skills'
if not skills_dir.exists() or not list(skills_dir.glob('*.md')):
    print('[VibeCheck] No proposed skills.')
    print()
    print('Skills are auto-proposed when VibeCheck spots a project convention used 3+ times.')
    print('Use /vibecheck-skills promote <name> to activate one.')
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

print('To activate a skill: /vibecheck-skills promote <name>')
print('To view a skill:     Read .vibecheck/proposed_skills/<name>.md')
"
```
