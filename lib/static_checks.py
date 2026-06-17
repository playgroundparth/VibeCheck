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
  - LAZY-01: native/stdlib reimplementation (uuid, node-fetch, cloneDeep, etc.)
  - LAZY-02: installed dependency ignored (reimplemented what package.json already provides)
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

# Patterns that indicate it's probably fine (env var usage, sanitization)
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
    # Injection false-positive guards
    r'sanitize',
    r'escape',
    r'validate',
    r'encodeURIComponent',
    r'parameterize',
    r'prepared',
    r'\.escape\(',
]

# ─── LAZY-01: native/stdlib reimplementation ─────────────────────────────────
# Curated list only. Each entry: (file_ext, regex, native_replacement, why)
# Only JS/TS for now — Python stdlib is rarely skipped in practice.
# Severity: HYGIENE (never blocking — it works, just adds unnecessary dep).

LAZY_NATIVE_PATTERNS = [
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"(?:require\(['\"]uuid['\"]|from ['\"]uuid['\"])"),
        "crypto.randomUUID()",
        "uuid is an external dependency for UUID generation. crypto.randomUUID() is native in Node ≥ 14.17 and all modern browsers — no package needed.",
    ),
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"(?:require\(['\"]node-fetch['\"]|from ['\"]node-fetch['\"])"),
        "fetch (native since Node 18)",
        "node-fetch is an external dependency. fetch is native since Node 18 and available in all modern browsers — the package is no longer needed.",
    ),
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"\.cloneDeep\b|(?:import|require).*cloneDeep"),
        "structuredClone()",
        "lodash.cloneDeep (or similar) is being used for deep cloning. structuredClone() is native since Node 17 and all modern browsers — no library needed.",
    ),
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"Math\.random\(\)\.toString\(36\)|Math\.random.*replace.*[a-z0-9]"),
        "crypto.randomUUID() or crypto.randomBytes()",
        "Math.random() is not cryptographically secure and should not be used for IDs, tokens, or nonces. Use crypto.randomUUID() for IDs or crypto.randomBytes() for tokens.",
    ),
    # JSON.parse/stringify for deep clone — structuredClone is native and handles more types
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"JSON\.parse\(JSON\.stringify\("),
        "structuredClone()",
        "JSON.parse(JSON.stringify(x)) is a hacky deep clone that drops undefined, Dates become strings, and it throws on circular refs. structuredClone() is native since Node 17 and handles all of these correctly.",
    ),
    # Custom base64 encode/decode in Node — Buffer is native
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"(?:require\(['\"](?:js-base64|base-64|base64-js)['\"]|from ['\"](?:js-base64|base-64|base64-js)['\"])"),
        "Buffer.from(x).toString('base64') / Buffer.from(x, 'base64').toString()",
        "An external base64 library is being used. Buffer.from() is native in Node — no package needed: Buffer.from(str).toString('base64') to encode, Buffer.from(b64, 'base64').toString() to decode.",
    ),
    # URL string concatenation — URL + URLSearchParams is native
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"['\"`][^'\"\`]{2,80}[?&][^'\"\`]*=.*['\"`]\s*\+|url\s*\+=.*[?&]"),
        "new URL(base) + url.searchParams.set(...)",
        "URLs are being built with string concatenation. Use new URL(base) and url.searchParams.set(key, value) — it handles encoding automatically and is easier to read.",
    ),
    # Custom array dedup — Set is native
    (
        {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
        re.compile(r"function (?:unique|dedup|dedupe|removeDuplicates|uniq)\b|filter\(.*indexOf\)|filter\(.*findIndex\)"),
        "[...new Set(arr)]",
        "A custom deduplication function is being written. [...new Set(arr)] is native and one line — no utility function needed.",
    ),
]

# ─── LAZY-02: installed dependency already covers this ────────────────────────
# Cross-references package.json to detect when a newly-written utility
# reimplements something an installed library already provides.
# Only flags new *utility/helper* files, not call sites.
# (regex to match installed pkg name, regex to match reimplemented pattern)

LAZY_INSTALLED_PATTERNS = [
    (
        re.compile(r"\b(?:date-fns|dayjs|moment|luxon)\b"),
        re.compile(r"function (?:format|formatDate|parseDate|toDateString|dateFormat)|const (?:format|formatDate|parseDate)"),
        "Date formatting",
        "A date library ({pkg}) is already installed. Use it instead of a custom date formatter.",
    ),
    (
        re.compile(r"\b(?:axios|got|ky|superagent|needle)\b"),
        re.compile(r"function (?:request|fetch|http|apiClient|makeRequest)|const (?:api|http|client)\s*=\s*\{[^}]*(?:get|post|put|delete)"),
        "HTTP client",
        "{pkg} is already installed. Use it directly instead of wrapping fetch in a custom client.",
    ),
    (
        re.compile(r"\b(?:lodash|lodash-es|remeda|radash)\b"),
        re.compile(r"function (?:chunk|groupBy|uniq|flatten|pick|omit|debounce|throttle|get)\b"),
        "Utility functions",
        "A utility library ({pkg}) is already installed. Use it instead of reimplementing {fn}.",
    ),
    # zod/joi/yup installed → custom validator object
    (
        re.compile(r"\b(?:zod|joi|yup|valibot|arktype)\b"),
        re.compile(r"function (?:validate|validateInput|validateSchema|validateBody|validateRequest)\b|const (?:schema|validator)\s*=\s*\{\s*(?:required|optional|type|min|max):"),
        "Schema validation",
        "{pkg} is already installed for schema validation. Use it instead of a custom validator — it handles error messages, type inference, and edge cases you'll otherwise have to add manually.",
    ),
    # winston/pino/bunyan installed → console.log in business logic
    (
        re.compile(r"\b(?:winston|pino|bunyan|log4js|loglevel)\b"),
        re.compile(r"console\.(?:log|warn|error|info|debug)\s*\([^)]{10,}"),
        "Structured logging",
        "{pkg} is already installed for logging. Use it instead of console.log — it adds log levels, structured output, and configurable transports that console.log can't do.",
    ),
    # p-retry/retry/axios-retry installed → custom retry loop
    (
        re.compile(r"\b(?:p-retry|retry|async-retry|axios-retry|got-retry)\b"),
        re.compile(r"for\s*\([^)]*attempt|while\s*\([^)]*retries|let retries|let attempts|retryCount"),
        "Retry logic",
        "{pkg} is already installed for retry logic. Use it instead of a custom retry loop — it handles exponential backoff, jitter, and abort signals that custom loops typically miss.",
    ),
]

# ─── Injection / unsafe patterns ─────────────────────────────────────────────
# High-confidence patterns only. Each entry: (regex, title, why, severity)

INJECTION_PATTERNS = [
    # SQL injection via string concatenation (JS/TS: "SELECT " + var)
    (
        r'(?:["\'`])SELECT\b[^"\'`\n]{0,120}"\s*\+|'
        r'(?:["\'`])SELECT\b[^"\'`\n]{0,120}\'\s*\+|'
        r'(?:["\'`])SELECT\b[^"\'`\n]{0,120}`\s*\+|'
        r'SELECT\b[^"\'\n]{0,80}"\s*\+\s*\w|'
        r'SELECT\b[^"\'\n]{0,80}\+\s*\w[^;]{0,30}(?:WHERE|FROM)',
        "SQL injection: query built with string concatenation",
        "User-controlled data concatenated into SQL string — attacker can exfiltrate or corrupt the database.",
        "CRITICAL",
    ),
    # Shell command injection
    (
        r'(?:execSync|exec|spawn)\s*\([^)]{0,60}\+\s*\w|'
        r'os\.system\s*\([^)]{0,60}\+|'
        r'subprocess\.(?:call|run|Popen)\s*\([^)]{0,80}\+',
        "Shell injection: command built with string concatenation",
        "User-controlled data in exec/execSync — attacker can run arbitrary shell commands on the server.",
        "CRITICAL",
    ),
    # Unsafe deserialization
    (
        r'pickle\.loads\s*\(|yaml\.load\s*\([^,)]*\)(?!\s*,\s*Loader)',
        "Unsafe deserialization: pickle.loads or yaml.load without SafeLoader",
        "Deserializing untrusted data with pickle or yaml.load allows arbitrary code execution.",
        "CRITICAL",
    ),
    # Open redirect
    (
        r'(?:res|response)\.redirect\s*\(\s*req\.(?:query|body|params)\.',
        "Open redirect: redirect target from user input",
        "Attacker can craft a link that redirects users to a malicious site (phishing, credential theft).",
        "PITFALL",
    ),
    # Timing-unsafe token comparison
    (
        r'(?:token|secret|api_?key|hash|hmac|signature)\s*[!=]==?\s*["\']|'
        r'["\'][^"\']*\'\s*[!=]==?\s*(?:token|secret|hash)',
        "Timing-unsafe comparison: use constant-time compare for secrets",
        "String equality on secrets leaks timing information — use crypto.timingSafeEqual or hmac.compare_digest.",
        "PITFALL",
    ),
    # Prototype pollution
    (
        r'Object\.assign\s*\(\s*\{[^}]*\}\s*,\s*req\.\w+\b|'
        r'\[\s*req\.(?:body|query|params)\.\w+\s*\]',
        "Prototype pollution: user input used as object key or spread target",
        "Merging req.body into an object with Object.assign allows attackers to pollute Object.prototype.",
        "PITFALL",
    ),
]

INJECTION_CHECK_EXTENSIONS = {'.js', '.ts', '.jsx', '.tsx', '.py', '.go', '.rb', '.php'}

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
        findings.extend(_check_injection_risks(file_path, content))
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

    # OPS-01: env vars used in code but absent from .env.example
    findings.extend(_check_env_vars_documented(cwd, changed_files))

    # LAZY-01: native/stdlib reimplementation
    for file_path in changed_files:
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        findings.extend(_check_lazy_native(file_path, content))

    # LAZY-02: installed dep already covers this (new utility files only)
    new_util_files = [
        f for f in changed_files
        if f.exists() and _is_utility_file(f)
    ]
    if new_util_files:
        findings.extend(_check_lazy_installed(cwd, new_util_files))

    # Architecture health checks
    findings.extend(run_arch_checks(cwd))

    return findings


# ─── LAZY-01 checker ──────────────────────────────────────────────────────────

def _check_lazy_native(file_path: Path, content: str) -> List[Dict]:
    """Flag use of external packages that have a direct native/stdlib replacement."""
    findings = []
    ext = file_path.suffix.lower()
    for exts, pattern, native, why in LAZY_NATIVE_PATTERNS:
        if ext not in exts:
            continue
        if pattern.search(content):
            findings.append({
                "severity": "HYGIENE",
                "title": f"Native replacement available: use {native} instead of external package in {file_path.name}",
                "file": str(file_path),
                "why": why,
                "fix_prompt": f'Replace the external import with {native}. No package install needed.',
                "source": "static",
                "tags": ["hygiene", "lazy", "dependencies"],
            })
    return findings


# ─── LAZY-02 checker ──────────────────────────────────────────────────────────

def _is_utility_file(file_path: Path) -> bool:
    """True if the file looks like a utility/helper module rather than a feature file."""
    name = file_path.stem.lower()
    parts = [p.lower() for p in file_path.parts]
    utility_dirs = {"utils", "util", "helpers", "helper", "lib", "common", "shared", "tools"}
    utility_names = {"utils", "util", "helpers", "helper", "common", "shared"}
    return any(p in utility_dirs for p in parts) or name in utility_names


def _check_lazy_installed(cwd: Path, util_files: List[Path]) -> List[Dict]:
    """Flag utility files that reimplement something an installed dep already provides."""
    import json
    findings = []

    pkg_json = cwd / "package.json"
    if not pkg_json.exists():
        return []
    try:
        pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    except Exception:
        return []

    all_deps = {
        **pkg.get("dependencies", {}),
        **pkg.get("devDependencies", {}),
    }

    for file_path in util_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pkg_pattern, fn_pattern, category, why_template in LAZY_INSTALLED_PATTERNS:
            installed = [name for name in all_deps if pkg_pattern.search(name)]
            if not installed:
                continue
            match = fn_pattern.search(content)
            if not match:
                continue
            pkg_name = installed[0]
            fn_name = match.group(0).split("function ")[-1].split("const ")[-1].split("(")[0].strip()
            why = why_template.replace("{pkg}", pkg_name).replace("{fn}", fn_name)
            findings.append({
                "severity": "HYGIENE",
                "title": f"{category} reimplemented in {file_path.name} — {pkg_name} is already installed",
                "file": str(file_path),
                "why": why,
                "fix_prompt": f'Remove the custom {fn_name} implementation and import the equivalent from {pkg_name}.',
                "source": "static",
                "tags": ["hygiene", "lazy", "dependencies"],
            })

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


def _check_injection_risks(file_path: Path, content: str) -> List[Dict]:
    """Check for injection vulnerabilities and unsafe patterns via regex."""
    if file_path.suffix not in INJECTION_CHECK_EXTENSIONS:
        return []

    # Skip test files — they often have intentionally dangerous patterns for testing
    name = file_path.name.lower()
    if any(x in name for x in ('.test.', '.spec.', '_test.', 'test_')):
        return []

    findings = []
    lines = content.split("\n")

    for pattern_str, title, why, severity in INJECTION_PATTERNS:
        compiled = re.compile(pattern_str, re.IGNORECASE | re.MULTILINE)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                continue
            if not compiled.search(line):
                continue
            # Check false-positive guards — if any guard matches the same line, skip
            if any(re.search(guard, line, re.IGNORECASE) for guard in FALSE_POSITIVE_GUARDS):
                continue
            fix = (
                f"There is a potential {title.split(':')[0].strip()} in {file_path.name} at line {i}. "
                f"Show me that line and I'll rewrite it safely."
            )
            findings.append({
                "severity": severity,
                "title": f"{title} in {file_path.name}",
                "file": f"{file_path}:{i}",
                "why": why,
                "fix_prompt": fix,
                "source": "static",
                "tags": ["security", "injection"],
            })
            break  # one finding per pattern per file

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


def _check_env_vars_documented(cwd: Path, changed_files: List[Path]) -> List[Dict]:
    """
    OPS-01: env var referenced in changed code but absent from .env.example.
    Grep-confirmable — no reasoning required, so this lives here not in the LLM layer.
    Only fires on source files (not .env.* files themselves).
    """
    # Patterns that extract variable names from code
    ENV_PATTERNS = [
        re.compile(r'process\.env\.([A-Z_][A-Z0-9_]+)'),            # JS/TS
        re.compile(r'os\.environ(?:\.get)?\([\'"]([A-Z_][A-Z0-9_]+)[\'"]'),  # Python
        re.compile(r'ENV\[[\'"]([A-Z_][A-Z0-9_]+)[\'"]\]'),         # Ruby
        re.compile(r'getenv\([\'"]([A-Z_][A-Z0-9_]+)[\'"]'),        # PHP/C
    ]
    # Auto-injected by platforms/shells — not meaningful to document
    SKIP_VARS = {
        "NODE_ENV", "PORT", "HOST", "PWD", "HOME", "USER", "PATH", "SHELL", "TZ",
        "CI", "GITHUB_ACTIONS", "VERCEL", "VERCEL_ENV", "VERCEL_URL",
        "RAILWAY_ENVIRONMENT", "FLY_APP_NAME", "RENDER", "HEROKU_APP_NAME",
        "npm_package_version", "npm_lifecycle_event",
    }
    SOURCE_EXTS = {'.js', '.ts', '.jsx', '.tsx', '.py', '.rb', '.php', '.go', '.rs'}

    # Find .env.example (various naming conventions)
    env_example_path = None
    for name in [".env.example", ".env.example.local", "env.example", ".env.template", ".env.sample"]:
        candidate = cwd / name
        if candidate.exists():
            env_example_path = candidate
            break

    # Collect vars used in changed source files
    vars_by_file: dict = {}  # var_name → [rel_path, ...]
    for file_path in changed_files:
        if not file_path.exists():
            continue
        if file_path.suffix not in SOURCE_EXTS:
            continue
        # Don't check .env files or config files for this
        if file_path.name.startswith(".env") or "env.example" in file_path.name:
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        found = set()
        for pat in ENV_PATTERNS:
            found.update(pat.findall(content))
        found -= SKIP_VARS
        if not found:
            continue
        try:
            rel = str(file_path.relative_to(cwd))
        except ValueError:
            rel = str(file_path)
        for var in found:
            vars_by_file.setdefault(var, []).append(rel)

    if not vars_by_file:
        return []

    findings = []

    if env_example_path is None:
        # No .env.example at all — flag once if any env vars are used
        findings.append({
            "severity": "HYGIENE",
            "title": "No .env.example — env vars not documented for deployment",
            "file": ".env.example",
            "why": (
                f"Code references {len(vars_by_file)} env var(s) "
                f"({', '.join(sorted(vars_by_file)[:3])}{'...' if len(vars_by_file) > 3 else ''}) "
                f"but no .env.example exists to document them."
            ),
            "fix_prompt": (
                "Create .env.example listing all required env vars with placeholder values. "
                "This file should be committed — it's documentation, not secrets. "
                f"Start with: {chr(10).join(f'{v}=' for v in sorted(vars_by_file))}"
            ),
            "source": "static",
            "tags": ["ops-01", "env-var"],
        })
        return findings

    # Parse vars declared in .env.example (VAR_NAME= or VAR_NAME=value or # VAR_NAME)
    example_content = env_example_path.read_text(encoding="utf-8", errors="ignore")
    example_vars = set(re.findall(r'^([A-Z_][A-Z0-9_]*)(?:\s*=.*)?$', example_content, re.MULTILINE))

    missing = {var: files for var, files in vars_by_file.items() if var not in example_vars}
    if not missing:
        return []

    for var, files in sorted(missing.items()):
        first_file = files[0]
        findings.append({
            "severity": "CRITICAL",
            "title": f"{var} used in code but missing from .env.example",
            "file": first_file,
            "why": (
                f"{var} is referenced in {first_file} but absent from "
                f"{env_example_path.name} — will be undefined in every environment that's not yours."
            ),
            "fix_prompt": (
                f"Add `{var}=<placeholder>` to {env_example_path.name}. "
                f"Then set the real value in your deployment environment "
                f"(Vercel dashboard → Settings → Environment Variables, Railway vars, etc.)."
            ),
            "source": "static",
            "tags": ["ops-01", "env-var"],
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


# ─── Architecture health checks ───────────────────────────────────────────────
# These are full-repo checks, not per-changed-file. They run during /vibecheck-scan
# via run_arch_checks(). All checks are deterministic — no LLM, no scoring, no
# composite metrics. Binary findings only: cycle exists or it doesn't, layer
# violation is present or it isn't.

_ARCH_SOURCE_EXTENSIONS = {
    '.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs',
    '.py', '.go', '.rb', '.php', '.rs', '.java', '.cs', '.kt', '.swift',
}

_ARCH_IGNORED_DIRS = {
    'node_modules', '.git', '.hg', 'dist', 'build', 'out', '.next', '.nuxt',
    '__pycache__', '.pytest_cache', '.mypy_cache', '.venv', 'venv', 'env',
    'coverage', 'htmlcov', '.tox', 'target', 'vendor', 'Pods', 'DerivedData',
    '.gradle', '.turbo', '.cache', 'generated', 'graphify-out', '.vibecheck',
    '.claude', '.agents', '.codex',
}

# Architecture layer definitions — matched against directory path segments
_INFRA_LAYER_SEGMENTS = {
    'infra', 'infrastructure', 'db', 'database',
    'repositories', 'adapters', 'clients', 'persistence',
}
_API_LAYER_SEGMENTS = {
    'api', 'routes', 'controllers', 'handlers', 'pages', 'endpoints',
}

# Files that are legitimate with zero importers (entry points, configs, etc.)
_DEAD_FILE_EXCLUSIONS = {
    'index.js', 'index.ts', 'index.jsx', 'index.tsx', 'index.mjs',
    'main.py', 'main.ts', 'main.js', 'main.go',
    'app.py', 'app.ts', 'app.js',
    'server.ts', 'server.js',
    '__init__.py', 'setup.py', 'conftest.py', 'manage.py',
    'cli.ts', 'cli.js', 'cli.py',
}
_DEAD_FILE_EXCL_PATTERNS = [
    re.compile(r'\.(test|spec)\.(ts|tsx|js|jsx|py|go)$'),
    re.compile(r'^test_|_test\.(py|go)$'),
    re.compile(r'\.(config|setup|stories)\.(ts|js|mjs|cjs)$'),
    re.compile(r'^(jest|vitest|webpack|vite|rollup|babel|eslint|prettier|next|nuxt)\.config\.'),
    re.compile(r'migration', re.IGNORECASE),
    re.compile(r'seed', re.IGNORECASE),
    re.compile(r'fixture', re.IGNORECASE),
]

# Relative import regexes — only local imports matter for the graph
_JS_LOCAL_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]*?\s+from\s+)?|require\s*\(\s*|import\s*\(\s*)['"](\.[^'"]+)['"]"""
)
_PY_LOCAL_IMPORT_RE = re.compile(
    r"""^\s*from\s+(\.[\w./]*)\s+import|^\s*import\s+(\.[\w./]+)""",
    re.MULTILINE,
)


def _arch_collect_files(cwd: Path) -> List[Path]:
    """Walk cwd and return all source files not in ignored dirs."""
    result = []
    for dirpath, dirnames, filenames in os.walk(str(cwd)):
        dirnames[:] = [d for d in dirnames if d not in _ARCH_IGNORED_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in _ARCH_SOURCE_EXTENSIONS:
                result.append(p)
    return result


def _arch_extract_imports(file_path: Path, content: str, cwd: Path) -> List[str]:
    """Extract resolved relative import paths from a source file."""
    ext = file_path.suffix.lower()
    current_dir = file_path.parent
    raw_specs: List[str] = []

    if ext == '.py':
        for m in _PY_LOCAL_IMPORT_RE.finditer(content):
            spec = m.group(1) or m.group(2)
            if spec:
                raw_specs.append(spec)
    else:
        raw_specs = [m.group(1) for m in _JS_LOCAL_IMPORT_RE.finditer(content)]

    resolved = []
    for spec in raw_specs:
        if not spec.startswith('.'):
            continue
        try:
            target = (current_dir / spec).resolve()
        except (OSError, ValueError):
            continue
        # Try exact path, then extensions, then index file
        candidates = [target]
        for ext2 in _ARCH_SOURCE_EXTENSIONS:
            candidates.append(target.with_suffix(ext2))
        for ext2 in _ARCH_SOURCE_EXTENSIONS:
            candidates.append(target / ('index' + ext2))
        for cand in candidates:
            try:
                if cand.is_file():
                    rel = str(cand.relative_to(cwd))
                    resolved.append(rel)
                    break
            except (OSError, ValueError):
                continue
    return resolved


def _arch_build_graph(cwd: Path, files: List[Path]) -> Dict[str, List[str]]:
    """Build {rel_path: [imported_rel_path, ...]} for all source files."""
    graph: Dict[str, List[str]] = {}
    for f in files:
        try:
            rel = str(f.relative_to(cwd))
        except ValueError:
            continue
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            content = ''
        graph[rel] = _arch_extract_imports(f, content, cwd)
    return graph


def _arch_tarjan_scc(graph: Dict[str, List[str]]) -> List[List[str]]:
    """Iterative Tarjan SCC. Returns only SCCs with ≥2 members (real cycles)."""
    index_counter = [0]
    stack: List[str] = []
    lowlinks: Dict[str, int] = {}
    indices: Dict[str, int] = {}
    on_stack: set = set()
    sccs: List[List[str]] = []

    def _visit(start: str) -> None:
        call_stack = [(start, iter(graph.get(start, [])))]
        indices[start] = index_counter[0]
        lowlinks[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)

        while call_stack:
            v, children = call_stack[-1]
            try:
                w = next(children)
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, iter(graph.get(w, []))))
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])
            except StopIteration:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlinks[parent] = min(lowlinks[parent], lowlinks[v])
                if lowlinks[v] == indices[v]:
                    scc: List[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        scc.append(w)
                        if w == v:
                            break
                    if len(scc) > 1:
                        sccs.append(scc)

    for node in list(graph.keys()):
        if node not in indices:
            _visit(node)
    return sccs


def _arch_fan_in(graph: Dict[str, List[str]]) -> Dict[str, int]:
    """Compute importer count per file."""
    counts: Dict[str, int] = {rel: 0 for rel in graph}
    for targets in graph.values():
        for t in targets:
            if t in counts:
                counts[t] += 1
    return counts


# ── Individual checkers ────────────────────────────────────────────────────────

def _check_arch_cycles(graph: Dict[str, List[str]]) -> List[Dict]:
    """ARCH-CYCLE: files forming circular dependencies."""
    findings = []
    for cycle in _arch_tarjan_scc(graph):
        cycle_sorted = sorted(cycle)
        short_names = [Path(f).name for f in cycle_sorted[:3]]
        extra = f' + {len(cycle_sorted) - 3} more' if len(cycle_sorted) > 3 else ''
        findings.append({
            'severity': 'PITFALL',
            'title': f'Dependency cycle: {" → ".join(short_names)}{extra} ({len(cycle_sorted)} files)',
            'file': cycle_sorted[0],
            'why': (
                f'These {len(cycle_sorted)} files form a circular dependency and cannot be changed '
                f'independently. Any bug fix ripples through the whole cycle.'
            ),
            'fix_prompt': (
                f'Break the cycle by moving the shared contract these files both need into a '
                f'lower-level module that neither depends on. '
                f'Cycle members: {", ".join(cycle_sorted)}'
            ),
            'source': 'static',
            'tags': ['architecture', 'arch-cycle'],
            'arch_cycle_members': cycle_sorted,
        })
    return findings


def _check_arch_god_files(graph: Dict[str, List[str]], cwd: Path, files: List[Path]) -> List[Dict]:
    """ARCH-GOD: files with outlier fan-in AND above-median LOC."""
    try:
        import statistics as _stats
        fan_in = _arch_fan_in(graph)
        fan_in_values = [v for v in fan_in.values() if v > 0]
        if len(fan_in_values) < 3:
            return []
        median_fi = _stats.median(fan_in_values)
        god_threshold = max(5, median_fi * 2)

        loc: Dict[str, int] = {}
        for f in files:
            try:
                rel = str(f.relative_to(cwd))
                loc[rel] = len(f.read_text(encoding='utf-8', errors='ignore').splitlines())
            except (OSError, ValueError):
                continue

        loc_values = sorted(loc.values())
        if not loc_values:
            return []
        loc_p75 = loc_values[int(len(loc_values) * 0.75)]

        findings = []
        for rel, count in sorted(fan_in.items(), key=lambda x: x[1], reverse=True):
            if count < god_threshold:
                break
            file_loc = loc.get(rel, 0)
            if file_loc < loc_p75:
                continue
            findings.append({
                'severity': 'PITFALL',
                'title': f'God-file candidate: {Path(rel).name} — {count} importers, {file_loc} lines',
                'file': rel,
                'why': (
                    f'{count} files depend on {Path(rel).name} ({file_loc} lines). '
                    f'Changes here have a large blast radius.'
                ),
                'fix_prompt': (
                    f'Split {Path(rel).name}: extract a narrow, stable public API (types, interfaces, '
                    f'pure functions) into a separate module. Dependents import the small interface, '
                    f'not the whole {file_loc}-line implementation. This shrinks blast radius immediately.'
                ),
                'source': 'static',
                'tags': ['architecture', 'arch-god'],
            })
        return findings
    except Exception:
        return []


def _check_arch_layer_violations(graph: Dict[str, List[str]]) -> List[Dict]:
    """ARCH-LAYER: infra-layer files importing from api-layer directories."""
    findings = []
    for src, targets in graph.items():
        src_parts = set(Path(src).parts)
        if not (src_parts & _INFRA_LAYER_SEGMENTS):
            continue
        for target in targets:
            tgt_parts = set(Path(target).parts)
            if tgt_parts & _API_LAYER_SEGMENTS:
                findings.append({
                    'severity': 'PITFALL',
                    'title': f'Layer violation: {Path(src).name} (infra) imports {Path(target).name} (api)',
                    'file': src,
                    'why': (
                        f'Infrastructure ({src}) depends on the API layer ({target}). '
                        f'This inverts the dependency direction.'
                    ),
                    'fix_prompt': (
                        f'Move what {Path(src).name} needs from {target} into a domain or shared '
                        f'module that both layers can import. The API layer should depend on infra, '
                        f'not the reverse.'
                    ),
                    'source': 'static',
                    'tags': ['architecture', 'arch-layer'],
                })
    return findings


def _check_arch_duplication(cwd: Path, files: List[Path], window: int = 6) -> List[Dict]:
    """ARCH-DUP: identical N-line normalised blocks appearing in 2+ files."""
    import hashlib as _hashlib

    window_hits: Dict[str, List[str]] = {}

    for f in files:
        try:
            rel = str(f.relative_to(cwd))
            content = f.read_text(encoding='utf-8', errors='ignore')
        except (OSError, ValueError):
            continue

        lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(('#', '//', '/*', '*', '"""', "'''")):
                continue
            lines.append(re.sub(r'\s+', ' ', stripped))

        if len(lines) < window:
            continue

        for i in range(len(lines) - window + 1):
            block = '\n'.join(lines[i:i + window])
            digest = _hashlib.sha1(block.encode('utf-8', errors='ignore')).hexdigest()
            if digest not in window_hits:
                window_hits[digest] = []
            if rel not in window_hits[digest]:
                window_hits[digest].append(rel)

    findings = []
    reported: set = set()
    for digest, locations in window_hits.items():
        unique_files = sorted(set(locations))
        if len(unique_files) < 2:
            continue
        key = tuple(unique_files)
        if key in reported:
            continue
        reported.add(key)

        short_names = [Path(f).name for f in unique_files[:3]]
        extra = f' + {len(unique_files) - 3} more' if len(unique_files) > 3 else ''
        findings.append({
            'severity': 'HYGIENE',
            'title': f'Duplicated {window}-line block in {", ".join(short_names)}{extra}',
            'file': unique_files[0],
            'why': (
                f'The same {window}-line block appears in {len(unique_files)} files: '
                f'{", ".join(unique_files)}. A bug fix must be applied in every copy.'
            ),
            'fix_prompt': (
                f'Extract the repeated block into a named helper. '
                f'Files with duplication: {", ".join(unique_files)}'
            ),
            'source': 'static',
            'tags': ['architecture', 'arch-dup', 'duplication'],
        })
        if len(findings) >= 5:
            break
    return findings


def _check_arch_dead_files(graph: Dict[str, List[str]], cwd: Path) -> List[Dict]:
    """ARCH-DEAD: source files with zero importers that are not entry points."""
    all_imported: set = set()
    for targets in graph.values():
        all_imported.update(targets)

    findings = []
    for rel in graph:
        if rel in all_imported:
            continue
        name = Path(rel).name
        if name in _DEAD_FILE_EXCLUSIONS:
            continue
        name_lower = name.lower()
        if any(p.search(name_lower) for p in _DEAD_FILE_EXCL_PATTERNS):
            continue
        try:
            head = (cwd / rel).read_text(encoding='utf-8', errors='ignore')[:300]
            if any(m in head for m in ('#!/', 'if __name__ == "__main__"', "if __name__ == '__main__'")):
                continue
        except OSError:
            continue
        findings.append({
            'severity': 'HYGIENE',
            'title': f'Dead file: {name} has no importers',
            'file': rel,
            'why': (
                f'{rel} is not imported by any other file. '
                f'It may be unreachable dead code.'
            ),
            'fix_prompt': (
                f'Confirm {rel} is intentionally standalone (entry point, CLI, migration, etc.). '
                f'If it is dead code, delete it — unused code has a maintenance cost and misleads '
                f'about what the system actually does.'
            ),
            'source': 'static',
            'tags': ['architecture', 'arch-dead', 'dead-code'],
        })
    return findings


def _check_arch_drift(cwd: Path, graph: Dict[str, List[str]]) -> List[Dict]:
    """ARCH-DRIFT: files whose fan-in increased significantly since the last scan."""
    import json as _json

    baseline_path = cwd / '.vibecheck' / 'arch_baseline.json'
    if not baseline_path.exists():
        return []
    try:
        baseline = _json.loads(baseline_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []

    prev_fan_in: Dict[str, int] = baseline.get('fan_in', {})
    if not prev_fan_in:
        return []

    current_fan_in = _arch_fan_in(graph)
    findings = []
    DRIFT_THRESHOLD = 5

    for rel, current in sorted(current_fan_in.items(), key=lambda x: x[1], reverse=True):
        prev = prev_fan_in.get(rel, 0)
        delta = current - prev
        if delta >= DRIFT_THRESHOLD:
            findings.append({
                'severity': 'PITFALL',
                'title': f'Coupling drift: {Path(rel).name} gained {delta} new importers since last scan',
                'file': rel,
                'why': (
                    f'{rel} had {prev} importers at last scan, now has {current}. '
                    f'It is accumulating dependents faster than it should.'
                ),
                'fix_prompt': (
                    f'Review what {Path(rel).name} exports. If many files need all of it, it is '
                    f'doing too much. Split into smaller focused modules before more dependents accumulate.'
                ),
                'source': 'static',
                'tags': ['architecture', 'arch-drift'],
            })
    return findings


def write_arch_baseline(cwd: Path, graph: Dict[str, List[str]]) -> None:
    """Persist a structural snapshot so the next scan can detect ARCH-DRIFT."""
    import json as _json
    import datetime as _dt
    import subprocess as _sp

    fan_in = _arch_fan_in(graph)
    cycles = _arch_tarjan_scc(graph)
    all_imported: set = set()
    for targets in graph.values():
        all_imported.update(targets)
    dead = [r for r in graph if r not in all_imported and Path(r).name not in _DEAD_FILE_EXCLUSIONS]

    git_head = None
    try:
        result = _sp.run(
            ['git', 'rev-parse', 'HEAD'], cwd=str(cwd),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_head = result.stdout.strip()
    except Exception:
        pass

    payload = {
        'scan_ts': _dt.datetime.now(_dt.timezone.utc).isoformat(),
        'git_head': git_head,
        'fan_in': fan_in,
        'cycle_count': len(cycles),
        'dead_files': dead[:50],
    }
    try:
        baseline_path = cwd / '.vibecheck' / 'arch_baseline.json'
        baseline_path.write_text(_json.dumps(payload, indent=2), encoding='utf-8')
    except OSError:
        pass


def run_arch_checks(cwd: Path) -> List[Dict]:
    """
    Full-repo architecture health checks. Called by /vibecheck-scan.
    Not called per-file — these need the whole import graph to be meaningful.
    Returns findings in the same schema as run_static_checks().
    """
    files = _arch_collect_files(cwd)
    if not files:
        return []

    graph = _arch_build_graph(cwd, files)

    findings: List[Dict] = []
    findings.extend(_check_arch_cycles(graph))
    findings.extend(_check_arch_god_files(graph, cwd, files))
    findings.extend(_check_arch_layer_violations(graph))
    findings.extend(_check_arch_duplication(cwd, files))
    findings.extend(_check_arch_dead_files(graph, cwd))
    findings.extend(_check_arch_drift(cwd, graph))

    # Write baseline for next scan's drift detection
    write_arch_baseline(cwd, graph)

    return findings
