"""
VibeCheck context extractor — zero LLM, pure regex.
Extracts security-relevant project facts from file content.
"""
import re
import json
import datetime
from pathlib import Path

# ── Patterns ────────────────────────────────────────────────────────────────

AUTH_PATTERNS = [
    (r"createClerkClient|@clerk/nextjs|@clerk/backend", "clerk"),
    (r"NextAuth|getServerSession|next-auth", "nextauth"),
    (r"createClient.*supabase|supabase.*createClient", "supabase"),
    (r"jwt\.verify|jsonwebtoken\.sign|jose\.jwtVerify", "custom-jwt"),
    (r"lucia\.validateSession|@lucia-auth", "lucia"),
]

AUTH_CHECK_PATTERNS = [
    r"auth\.getUser\(\)",
    r"getServerSession\(",
    r"currentUser\(\)",
    r"requireAuth\(",
    r"protectedProcedure",
    r"ctx\.session(?:\.user)?",
    r"session\s*\?\??\s*redirect|redirect.*login",
]

WEBHOOK_PATTERNS = [
    (r"stripe\.webhooks\.constructEvent|webhooks\.constructEvent", "stripe", True),
    (r"svix\.Webhook|wh\.verify\(", "svix", True),
    (r"crypto\.timingSafeEqual", "custom", True),
    (r"JSON\.parse\(body\).*Stripe|Stripe.*JSON\.parse\(body\)", "stripe", False),
]

ORM_PATTERNS = [
    (r"from ['\"]prisma|PrismaClient|prisma\.\w+\.\w+", "prisma"),
    (r"drizzle-orm|from ['\"]drizzle", "drizzle"),
    (r"from ['\"]@supabase|supabase\.from\(", "supabase"),
    (r"\bpg\.query\b|new Pool\(|\.query\(['\"]SELECT", "raw-sql"),
]

STACK_PATTERNS = [
    (r"from ['\"]next/|next\.config", "nextjs"),
    (r"@remix-run", "remix"),
    (r"from ['\"]@trpc|createTRPCRouter|initTRPC", "trpc"),
    (r"from ['\"]express|express\(\)", "express"),
    (r"from ['\"]hono|new Hono\(\)", "hono"),
    (r"from ['\"]stripe|new Stripe\(", "stripe"),
    (r"resend|nodemailer|sendgrid", "email"),
]

RISK_PATTERNS = [
    (r"supabaseAnonKey|NEXT_PUBLIC_SUPABASE_ANON_KEY.*service|anonKey.*admin",
     "anon key used where service role expected"),
    (r"process\.env\.\w+\s*(?:||)\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
     "hardcoded credential fallback"),
    (r"dangerouslySetInnerHTML",
     "XSS risk: dangerouslySetInnerHTML"),
    (r"eval\s*\(|new Function\s*\(",
     "code injection risk: eval/new Function"),
]

# ── Main extraction function ─────────────────────────────────────────────────

def extract(file_path: str, content: str) -> dict:
    """Return a dict of facts extracted from this file."""
    facts = {}
    rel = file_path

    # Auth provider
    for pattern, provider in AUTH_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            facts["auth_provider"] = provider
            break

    # Auth checks present
    for pattern in AUTH_CHECK_PATTERNS:
        if re.search(pattern, content):
            facts.setdefault("auth_check_files", [])
            if rel not in facts["auth_check_files"]:
                facts["auth_check_files"] = [rel]
            break

    # Service role usage
    if re.search(r"serviceRoleKey|service_role|SUPABASE_SERVICE", content):
        facts.setdefault("service_role_files", [])
        facts["service_role_files"] = [rel]

    # Webhook verification
    for pattern, provider, verified in WEBHOOK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            key = f"webhook_{provider}"
            facts[key] = {"verified": verified, "file": rel}
            break

    # ORM / DB layer
    for pattern, orm in ORM_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            facts["orm"] = orm
            break

    # Stack detection
    stack_hits = []
    for pattern, tech in STACK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            stack_hits.append(tech)
    if stack_hits:
        facts["stack_hints"] = stack_hits

    # Risk patterns
    risks = []
    for pattern, note in RISK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            risks.append({"file": rel, "note": note})
    if risks:
        facts["risks"] = risks

    return facts


# ── Merge into project_context.json ─────────────────────────────────────────

def update_context(vg_dir: Path, file_path: str, content: str) -> None:
    """Extract facts from a file and merge into project_context.json."""
    facts = extract(file_path, content)
    if not facts:
        return

    ctx_path = vg_dir / "project_context.json"
    ctx = {}
    if ctx_path.exists():
        try:
            ctx = json.loads(ctx_path.read_text())
        except Exception:
            ctx = {}

    # Merge facts in
    if "auth_provider" in facts and not ctx.get("auth", {}).get("provider"):
        ctx.setdefault("auth", {})["provider"] = facts["auth_provider"]

    if "auth_check_files" in facts:
        ctx.setdefault("auth", {}).setdefault("check_files", [])
        for f in facts["auth_check_files"]:
            if f not in ctx["auth"]["check_files"]:
                ctx["auth"]["check_files"].append(f)

    if "service_role_files" in facts:
        ctx.setdefault("auth", {}).setdefault("service_role_files", [])
        for f in facts["service_role_files"]:
            if f not in ctx["auth"]["service_role_files"]:
                ctx["auth"]["service_role_files"].append(f)

    for key in ["webhook_stripe", "webhook_svix", "webhook_custom"]:
        if key in facts:
            ctx.setdefault("webhooks", {})[key] = facts[key]

    if "orm" in facts:
        ctx.setdefault("db", {})["orm"] = facts["orm"]

    if "stack_hints" in facts:
        existing = set(ctx.get("stack", []))
        existing.update(facts["stack_hints"])
        ctx["stack"] = sorted(existing)

    if "risks" in facts:
        existing_notes = {r["note"] for r in ctx.get("risk_patterns", [])}
        for r in facts["risks"]:
            if r["note"] not in existing_notes:
                ctx.setdefault("risk_patterns", []).append(r)
                existing_notes.add(r["note"])

    ctx["files_scanned"] = ctx.get("files_scanned", 0) + 1
    ctx["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    try:
        ctx_path.write_text(json.dumps(ctx, indent=2))
    except Exception:
        pass


# ── Summary for injection ────────────────────────────────────────────────────

def summarize(vg_dir: Path) -> str:
    """Return a one-line summary of project_context for Claude's context."""
    ctx_path = vg_dir / "project_context.json"
    if not ctx_path.exists():
        return ""
    try:
        ctx = json.loads(ctx_path.read_text())
    except Exception:
        return ""

    parts = []

    auth = ctx.get("auth", {})
    if auth.get("provider"):
        parts.append(f"auth:{auth['provider']}")
    if auth.get("check_files"):
        parts.append("auth-checks:present")

    webhooks = ctx.get("webhooks", {})
    for k, v in webhooks.items():
        provider = k.replace("webhook_", "")
        verified = v.get("verified", False)
        parts.append(f"webhook-{provider}:{'verified' if verified else '⚠️ UNVERIFIED'}")

    db = ctx.get("db", {})
    if db.get("orm"):
        parts.append(f"db:{db['orm']}")

    stack = ctx.get("stack", [])
    if stack:
        parts.append(f"stack:{'+'.join(stack[:4])}")

    risks = ctx.get("risk_patterns", [])
    if risks:
        parts.append(f"⚠️ {len(risks)} known risk(s)")

    if not parts:
        return ""

    scanned = ctx.get("files_scanned", 0)
    return f"[VibeCheck] Project context ({scanned} files): {' · '.join(parts)}"
