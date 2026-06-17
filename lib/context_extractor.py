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

# ── Integration detection ────────────────────────────────────────────────────
# Maps integration name → (detection regex, is_webhook_file regex or None)
INTEGRATION_DETECTION = {
    "stripe": (r"from ['\"]stripe|new Stripe\(|stripe\.webhooks\.", r"webhook.*stripe|stripe.*webhook"),
    "supabase": (r"createClient.*supabase|supabase.*createClient|@supabase/supabase-js", r"webhook.*supabase"),
    "openai": (r"from ['\"]openai|new OpenAI\(|openai\.chat\.completions|anthropic|from ['\"]@anthropic", None),
    "clerk": (r"createClerkClient|@clerk/nextjs|@clerk/backend|clerkMiddleware", None),
    "prisma": (r"from ['\"]@prisma/client|PrismaClient|prisma\.\w+\.\w+", None),
    "vercel": (r"vercel\.json|from ['\"]@vercel|VERCEL_URL|VERCEL_ENV", None),
    "resend": (r"from ['\"]resend|new Resend\(", None),
    "inngest": (r"from ['\"]inngest|createFunction.*inngest|inngest\.createFunction", None),
}

# Static knowledge per integration — requirements and fix hints for the review planner
INTEGRATION_KNOWLEDGE = {
    "stripe": {
        "known_requirements": ["signature verification via constructEvent", "idempotency on event.id", "server-side amount derivation"],
        "fix_hints": {
            "signature": "Use stripe.webhooks.constructEvent(rawBody, sig, secret) — NOT the parsed body",
            "idempotency": "Check stripe_event_id in DB before processing; return 200 if already seen",
            "amount": "Always compute charge amount from your price table server-side — never trust req.body.amount"
        }
    },
    "supabase": {
        "known_requirements": ["use getUser() not getSession() for auth (getSession() is not network-validated)", "service role key must never reach the client"],
        "fix_hints": {
            "auth": "Use supabase.auth.getUser() not getSession() — getSession() trusts unvalidated local storage",
            "service_role": "service role key must only appear in server-side code, never in NEXT_PUBLIC_ env vars"
        }
    },
    "openai": {
        "known_requirements": ["API key must not appear in client-side code", "set explicit timeout on completions calls", "check finish_reason before using completion"],
        "fix_hints": {
            "timeout": "Pass signal: AbortSignal.timeout(30000) to completions.create() — LLM calls can hang indefinitely",
            "finish_reason": "Check choice.finish_reason === 'stop' before using output — 'length' means truncated"
        }
    },
    "clerk": {
        "known_requirements": ["auth() or currentUser() called before any data access", "middleware must protect all app routes"],
        "fix_hints": {
            "auth": "Call auth() at the top of server components/actions before any DB query",
            "middleware": "Ensure middleware.ts covers all protected routes — check matcher config"
        }
    },
    "prisma": {
        "known_requirements": ["use single PrismaClient instance (not new PrismaClient per request)", "always handle Prisma errors — they throw on constraint violations"],
        "fix_hints": {
            "singleton": "Export a singleton: const prisma = global.prisma ?? new PrismaClient() — instantiating per-request leaks connections",
        }
    },
}

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

    # Integration detection
    integrations_found = {}
    for name, (sdk_pattern, webhook_pattern) in INTEGRATION_DETECTION.items():
        if re.search(sdk_pattern, content, re.IGNORECASE):
            entry = integrations_found.setdefault(name, {"sdk_files": [], "webhook_paths": []})
            entry["sdk_files"].append(rel)
        if webhook_pattern and re.search(webhook_pattern, rel, re.IGNORECASE):
            entry = integrations_found.setdefault(name, {"sdk_files": [], "webhook_paths": []})
            entry["webhook_paths"].append(rel)
    if integrations_found:
        facts["integrations"] = integrations_found

    return facts


# ── Merge into project_context.json ─────────────────────────────────────────

def update_context(vc_dir: Path, file_path: str, content: str) -> None:
    """Extract facts from a file and merge into project_context.json."""
    facts = extract(file_path, content)
    if not facts:
        return

    ctx_path = vc_dir / "project_context.json"
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

    # Merge integrations
    if "integrations" in facts:
        ctx_integrations = ctx.setdefault("integrations", {})
        for name, data in facts["integrations"].items():
            entry = ctx_integrations.setdefault(name, {
                "sdk_files": [],
                "webhook_paths": [],
                **INTEGRATION_KNOWLEDGE.get(name, {}),
            })
            for f in data.get("sdk_files", []):
                if f not in entry.get("sdk_files", []):
                    entry.setdefault("sdk_files", []).append(f)
            for f in data.get("webhook_paths", []):
                if f not in entry.get("webhook_paths", []):
                    entry.setdefault("webhook_paths", []).append(f)

    ctx["files_scanned"] = ctx.get("files_scanned", 0) + 1
    ctx["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    try:
        ctx_path.write_text(json.dumps(ctx, indent=2))
    except Exception:
        pass


# ── Summary for injection ────────────────────────────────────────────────────

def summarize(vc_dir: Path) -> str:
    """Return a one-line summary of project_context for Claude's context."""
    ctx_path = vc_dir / "project_context.json"
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
