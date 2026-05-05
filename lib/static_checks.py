#!/usr/bin/env python3
"""
VibeCheck static checks — zero LLM, zero cost.
These run synchronously in the stop hook before firing the async LLM analyzer.
Fast: completes in <100ms even on large files.

Catches:
  - Hardcoded secrets / API keys (regex)
  - .env files accidentally committed
  - node_modules or build artifacts not in .gitignore
  - Missing .gitignore entirely
  - README.md missing or empty
  - Very large files committed (likely generated/binary)
  - console.log with suspicious content
  - TODO/FIXME density (code quality signal)
  - package.json / requirements.txt without lock file
  - Direct use of 'eval(' in JS/Python
"""

import re
import os
from pathlib import Path
from typing import List, Dict


# ─── Secret patterns (regex) ──────────────────────────────────────────────────
# Ordered by confidence. Only flag high-confidence matches to keep FP rate low.

SECRET_PATTERNS = [
    # AWS
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key ID hardcoded in source file"),
    (r'aws_secret_access_key\s*=\s*["\'][^"\']{20,}["\']', "AWS Secret Key hardcoded"),
    # Stripe
    (r'sk_live_[0-9a-zA-Z]{24,}', "Stripe live secret key hardcoded — anyone can charge your account"),
    (r'sk_test_[0-9a-zA-Z]{24,}', "Stripe test secret key hardcoded"),
    # Generic API key patterns (high confidence only)
    (r'(?i)(api_key|apikey|api_secret)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{20,}["\']', "API key or secret hardcoded"),
    # JWT secrets
    (r'(?i)(jwt_secret|jwt_key|secret_key)\s*[=:]\s*["\'][^"\']{8,}["\']', "JWT secret hardcoded"),
    # Database URLs with credentials
    (r'(?i)(postgres|mysql|mongodb)://[^:]+:[^@]+@', "Database connection string with credentials hardcoded"),
    # OpenAI
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key possibly hardcoded"),
    # GitHub tokens
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub Personal Access Token hardcoded"),
    (r'github_pat_[a-zA-Z0-9_]{82}', "GitHub Fine-grained PAT hardcoded"),
    # Generic password assignments
    (r'(?i)password\s*=\s*["\'][^"\']{6,}["\']', "Password hardcoded in source (not from env)"),
]

# Patterns that indicate it's probably fine (env var usage)
FALSE_POSITIVE_GUARDS = [
    r'process\.env\.',
    r'os\.environ',
    r'os\.getenv',
    r'config\.',
    r'settings\.',
    r'\$\{',           # template literals
    r'YOUR_',          # placeholder
    r'<YOUR',
    r'example',
    r'placeholder',
    r'REPLACE',
]

# File extensions to check for secrets
SECRET_CHECK_EXTENSIONS = {
    '.js', '.ts', '.jsx', '.tsx', '.py', '.go', '.rb', '.php',
    '.java', '.cs', '.env', '.yaml', '.yml', '.toml', '.json',
    '.sh', '.bash', '.zsh', '.env.local', '.env.development',
}

# File extensions to skip (binary, too large, etc.)
SKIP_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2',
    '.ttf', '.eot', '.mp4', '.mp3', '.pdf', '.zip', '.tar', '.gz',
    '.lock',  # lock files are fine to have secrets in (hashes, not real secrets)
}

MAX_FILE_SIZE_BYTES = 500_000  # 500KB — skip analysis of huge files


# ─── Main entry point ────────────────────────────────────────────────────────

def run_static_checks(cwd: Path, changed_files: List[Path]) -> List[Dict]:
    """
    Run all static checks against changed files + project structure.
    Returns list of finding dicts (same schema as store.add_finding expects).
    Fast — no network, no LLM.
    """
    findings = []

    # Per-file checks
    for file_path in changed_files:
        if not file_path.exists():
            continue
        if file_path.suffix in SKIP_EXTENSIONS:
            continue
        if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
            findings.append(_large_file_finding(file_path))
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        findings.extend(_check_secrets(file_path, content))
        findings.extend(_check_eval_usage(file_path, content))
        findings.extend(_check_console_log_secrets(file_path, content))
        findings.extend(_check_todo_density(file_path, content))
        findings.extend(_check_env_file_committed(file_path))

    # Project-level checks (run once regardless of what changed)
    findings.extend(_check_gitignore(cwd))
    findings.extend(_check_readme(cwd))
    findings.extend(_check_lockfile(cwd))
    findings.extend(_check_gitignore_coverage(cwd))

    # Dead code: new files with no callers
    findings.extend(_check_orphaned_new_files(cwd, changed_files))

    return findings


# ─── Per-file checks ──────────────────────────────────────────────────────────

def _check_secrets(file_path: Path, content: str) -> List[Dict]:
    findings = []
    lines = content.split("\n")

    for pattern, description in SECRET_PATTERNS:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                # Check false positive guards
                if any(re.search(guard, line) for guard in FALSE_POSITIVE_GUARDS):
                    continue
                # Skip comment lines
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                    continue

                findings.append({
                    "severity": "CRITICAL",
                    "title": description,
                    "file": f"{file_path}:{i}",
                    "why": "Anyone who can read your code (GitHub, teammates, hackers) can use this key. Real money and data at risk.",
                    "fix_prompt": (
                        f"There's a hardcoded secret in {file_path.name} line {i}. "
                        f"Move it to an environment variable: create a .env file, add the key there "
                        f"(like MY_KEY=actual_value), add .env to .gitignore, then read it in code with "
                        f"process.env.MY_KEY (Node) or os.environ['MY_KEY'] (Python). "
                        f"Then remove the hardcoded value."
                    ),
                    "source": "static",
                    "tags": ["secrets", "security"],
                })
                break  # One finding per pattern per file is enough

    return findings


def _check_eval_usage(file_path: Path, content: str) -> List[Dict]:
    if file_path.suffix not in {'.js', '.ts', '.jsx', '.tsx', '.py'}:
        return []

    findings = []
    lines = content.split("\n")

    eval_pattern = re.compile(r'\beval\s*\(')
    exec_pattern = re.compile(r'\bexec\s*\(')  # Python

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        if eval_pattern.search(line) or (file_path.suffix == '.py' and exec_pattern.search(line)):
            findings.append({
                "severity": "CRITICAL",
                "title": f"eval() used in {file_path.name} — dangerous if user input reaches it",
                "file": f"{file_path}:{i}",
                "why": "If any user-controlled data reaches eval(), attackers can run arbitrary code on your server.",
                "fix_prompt": (
                    f"There's an eval() call in {file_path.name} at line {i}. "
                    f"Tell me what this eval() is doing and I'll rewrite it safely without eval."
                ),
                "source": "static",
                "tags": ["security", "injection"],
            })
            break

    return findings


def _check_console_log_secrets(file_path: Path, content: str) -> List[Dict]:
    if file_path.suffix not in {'.js', '.ts', '.jsx', '.tsx'}:
        return []

    findings = []
    lines = content.split("\n")
    suspicious = re.compile(
        r'console\.(log|debug|info)\s*\(.*?(password|token|secret|key|auth|credential)',
        re.IGNORECASE
    )

    for i, line in enumerate(lines, 1):
        if suspicious.search(line):
            findings.append({
                "severity": "GOOD_TO_HAVE",
                "title": f"Sensitive data may be logged to console in {file_path.name}",
                "file": f"{file_path}:{i}",
                "why": "Console logs can be visible in browser DevTools, server logs, or error tracking services.",
                "fix_prompt": (
                    f"Remove or redact the console.log on line {i} of {file_path.name} "
                    f"that may be logging sensitive data (password, token, key, etc.)."
                ),
                "source": "static",
                "tags": ["hygiene", "security"],
            })
            break

    return findings


def _check_todo_density(file_path: Path, content: str) -> List[Dict]:
    """Flag files with very high TODO/FIXME/HACK density."""
    lines = content.split("\n")
    total = len(lines)
    if total < 20:
        return []

    todo_pattern = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE)
    todo_count = sum(1 for line in lines if todo_pattern.search(line))
    density = todo_count / total

    if density > 0.05 and todo_count >= 5:  # >5% density and at least 5 TODOs
        return [{
            "severity": "HYGIENE",
            "title": f"{file_path.name} has {todo_count} unresolved TODO/FIXME comments ({int(density*100)}% of file)",
            "file": str(file_path),
            "why": "High TODO density usually means incomplete code shipped to production. These often become real bugs.",
            "fix_prompt": (
                f"Review the TODO and FIXME comments in {file_path.name}. "
                f"For each one: either implement it now, create a tracking issue for it, or delete it if it's no longer relevant."
            ),
            "source": "static",
            "tags": ["hygiene", "completeness"],
        }]
    return []


def _check_env_file_committed(file_path: Path) -> List[Dict]:
    """Flag if an actual .env file (not .env.example) is being written."""
    name = file_path.name
    if name == ".env" or (name.startswith(".env.") and "example" not in name and "sample" not in name):
        return [{
            "severity": "CRITICAL",
            "title": f"{name} file written — this should never be committed to git",
            "file": str(file_path),
            "why": "Real .env files contain secrets. If committed to git (even briefly), they can be exposed forever.",
            "fix_prompt": (
                f"Make sure {name} is in your .gitignore right now. "
                f"Run: echo '{name}' >> .gitignore && git rm --cached {name} (if already tracked). "
                f"Create a {name}.example file with fake placeholder values instead."
            ),
            "source": "static",
            "tags": ["secrets", "security", "critical"],
        }]
    return []


def _large_file_finding(file_path: Path) -> Dict:
    size_kb = file_path.stat().st_size // 1024
    return {
        "severity": "HYGIENE",
        "title": f"Large file committed: {file_path.name} ({size_kb}KB)",
        "file": str(file_path),
        "why": "Large files slow down git, inflate repo size, and are often generated files that shouldn't be committed.",
        "fix_prompt": (
            f"{file_path.name} is {size_kb}KB. Is this a generated file, build output, or binary? "
            f"If so, add it to .gitignore. If it must be in the repo, explain why."
        ),
        "source": "static",
        "tags": ["hygiene", "repo-size"],
    }


# ─── Project-level checks ─────────────────────────────────────────────────────

def _check_gitignore(cwd: Path) -> List[Dict]:
    gitignore = cwd / ".gitignore"
    if not gitignore.exists():
        return [{
            "severity": "HYGIENE",
            "title": "No .gitignore file in project",
            "file": ".gitignore",
            "why": "Without .gitignore, node_modules, build files, .env, and other junk will end up in your git history.",
            "fix_prompt": (
                "Create a .gitignore file. Ask me: 'Create a .gitignore for my project' and I'll make one "
                "appropriate for your tech stack."
            ),
            "source": "static",
            "tags": ["hygiene", "repo"],
        }]
    return []


def _check_gitignore_coverage(cwd: Path) -> List[Dict]:
    """Check that common generated dirs are in .gitignore."""
    gitignore = cwd / ".gitignore"
    if not gitignore.exists():
        return []

    content = gitignore.read_text(errors="ignore")
    findings = []

    # node_modules should be ignored if package.json exists
    if (cwd / "package.json").exists() and "node_modules" not in content:
        findings.append({
            "severity": "HYGIENE",
            "title": "node_modules/ not in .gitignore",
            "file": ".gitignore",
            "why": "node_modules is huge (often 100MB+) and should never be in git.",
            "fix_prompt": "Add 'node_modules/' to your .gitignore file.",
            "source": "static",
            "tags": ["hygiene", "repo"],
        })

    # .env files
    if ".env" not in content:
        findings.append({
            "severity": "CRITICAL",
            "title": ".env not in .gitignore — secrets could be committed",
            "file": ".gitignore",
            "why": "If .env is ever committed, your API keys, database passwords, and other secrets become part of git history permanently.",
            "fix_prompt": "Add '.env' and '.env.local' to your .gitignore file right now.",
            "source": "static",
            "tags": ["secrets", "security"],
        })

    # Build outputs
    build_dirs = [("dist/", "dist"), ("build/", "build"), (".next/", ".next")]
    for pattern, dirname in build_dirs:
        if (cwd / dirname).exists() and pattern not in content:
            findings.append({
                "severity": "HYGIENE",
                "title": f"{dirname}/ build output not in .gitignore",
                "file": ".gitignore",
                "why": f"The {dirname}/ directory is generated by your build process and shouldn't be in git.",
                "fix_prompt": f"Add '{pattern}' to your .gitignore file.",
                "source": "static",
                "tags": ["hygiene", "repo"],
            })

    return findings


def _check_readme(cwd: Path) -> List[Dict]:
    readme = cwd / "README.md"
    if not readme.exists():
        return [{
            "severity": "HYGIENE",
            "title": "No README.md in project",
            "file": "README.md",
            "why": "Without a README, you (or anyone helping you) won't know how to set up or run the project in 3 months.",
            "fix_prompt": (
                "Create a README.md for this project. Include: what it does, how to set it up locally, "
                "what environment variables are needed, and how to run it."
            ),
            "source": "static",
            "tags": ["hygiene", "documentation"],
        }]

    content = readme.read_text(errors="ignore").strip()
    if len(content) < 100:
        return [{
            "severity": "HYGIENE",
            "title": "README.md exists but is nearly empty",
            "file": "README.md",
            "why": "A minimal README means no one (including future you) will know how to set up or use this project.",
            "fix_prompt": (
                "Update README.md to include: what this project does, how to install and run it, "
                "what environment variables are needed, and any important notes."
            ),
            "source": "static",
            "tags": ["hygiene", "documentation"],
        }]
    return []


def _check_orphaned_new_files(cwd: Path, changed_files: List[Path]) -> List[Dict]:
    """
    Flag source files that were just created but nothing in the project imports them.
    Uses project_map reverse_deps for O(1) lookup after an incremental map update.
    Only flags files that are new (not previously in the map) to avoid noise on existing code.
    """
    SOURCE_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rb'}
    SKIP_NAMES = {
        "index.js", "index.ts", "index.jsx", "index.tsx",
        "main.py", "app.py", "server.ts", "server.js",
        "__init__.py", "setup.py", "conftest.py",
    }
    SKIP_PATTERNS = [
        re.compile(r'^test_'),
        re.compile(r'_test\.py$'),
        re.compile(r'\.(test|spec)\.(ts|tsx|js|jsx)$'),
        re.compile(r'\.(config|setup)\.(ts|js|mjs|cjs)$'),
        re.compile(r'^(jest|vitest|webpack|vite|rollup|babel|eslint|prettier)\.'),
    ]

    # Lazy import — keeps static_checks fast if project_map is absent
    try:
        import project_map as pm
    except ImportError:
        return []

    map_data = pm.load_map(cwd)
    if not map_data:
        return []

    existing_files = set(map_data.get("files", {}).keys())
    new_source_files = []

    for f in changed_files:
        if not f.exists() or f.suffix not in SOURCE_EXTS:
            continue
        if f.name in SKIP_NAMES:
            continue
        name_lower = f.name.lower()
        if any(p.search(name_lower) for p in SKIP_PATTERNS):
            continue
        # Skip entry-point scripts
        try:
            head = f.read_text(encoding="utf-8", errors="ignore")[:200]
            if '#!/' in head or 'if __name__ == "__main__"' in head:
                continue
        except Exception:
            continue
        try:
            rel = str(f.relative_to(cwd))
        except ValueError:
            continue
        if rel not in existing_files:
            new_source_files.append(f)

    if not new_source_files:
        return []

    # Update map to capture new files and rebuild reverse_deps
    try:
        updated = pm.update_map_for_files(cwd, new_source_files)
    except Exception:
        return []

    reverse_deps = updated.get("reverse_deps", {})
    findings = []

    for f in new_source_files:
        try:
            rel = str(f.relative_to(cwd))
        except ValueError:
            continue
        callers = reverse_deps.get(rel, [])
        if not callers:
            findings.append({
                "severity": "PITFALL",
                "title": f"{f.name} added but nothing imports it",
                "file": rel,
                "why": "No callers found — this file ships as dead code unless something imports it",
                "fix_prompt": (
                    f"{f.name} was just created but no other file imports it. "
                    f"Either import it where it's needed, or delete it if it was created by mistake."
                ),
                "source": "static",
                "tags": ["dead-code"],
            })

    return findings


def _check_lockfile(cwd: Path) -> List[Dict]:
    """Flag if package.json exists but no lock file."""
    if not (cwd / "package.json").exists():
        return []

    has_lock = any([
        (cwd / "package-lock.json").exists(),
        (cwd / "yarn.lock").exists(),
        (cwd / "pnpm-lock.yaml").exists(),
        (cwd / "bun.lockb").exists(),
    ])

    if not has_lock:
        return [{
            "severity": "HYGIENE",
            "title": "No package lock file (package-lock.json / yarn.lock)",
            "file": "package.json",
            "why": "Without a lock file, npm install can pull different versions each time, causing 'works on my machine' problems.",
            "fix_prompt": "Run 'npm install' (or yarn/pnpm install) to generate a lock file, then commit it.",
            "source": "static",
            "tags": ["hygiene", "reliability"],
        }]
    return []
