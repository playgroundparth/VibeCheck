# Golden: Intentional MVP Tradeoff → ⚠️ (NOT ❌)

## Scenario

Developer adds an in-memory rate limiter. The code has a `// MVP` comment calling it out explicitly. The developer knows it won't survive restarts — they've made a deliberate tradeoff to ship faster. The production path for this (Redis) is noted in a TODO.

## What Changed

```
lib/rate-limit.ts   ← new file, in-memory Map counter
```

## Evidence Found

`lib/rate-limit.ts`:
```ts
// MVP: in-memory only — won't survive restarts, replace with Redis before prod launch
const counters = new Map<string, { count: number; resetAt: number }>();

export function checkRateLimit(ip: string, limit = 100): boolean {
  const now = Date.now();
  const entry = counters.get(ip) ?? { count: 0, resetAt: now + 60_000 };

  if (now > entry.resetAt) {
    entry.count = 0;
    entry.resetAt = now + 60_000;
  }

  entry.count++;
  counters.set(ip, entry);

  return entry.count <= limit;
}
```

The comment clearly states the tradeoff. No Redis is installed yet.

## Expected VibeCheck Output

**Finding (evidence-anchored):**
```json
{
  "severity": "PITFALL",
  "title": "In-memory rate limiter resets on every server restart",
  "file": "lib/rate-limit.ts:2",
  "files_read": ["lib/rate-limit.ts"],
  "why": "Counters live in RAM — any deploy, crash, or scale-out resets all limits to zero"
}
```

**Footer:**
```
---
VibeCheck: ⚠️ OK for MVP, not prod · ⚡ 1 pitfall
🧪 Before shipping: restart the server mid-window and confirm the counter resets — document this as a known gap in your ops runbook
💡 The TODO is the right call — ship it, but Redis is one deploy away and this is the first thing that breaks under load
```

## Global Invariant

- **verdict is present** — ⚠️ OK for MVP, not prod
- **verdict answers "can I continue?"** — yes for MVP; no for production

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce ❌ Fix before shipping — this is labeled, intentional, and survivable for MVP
- ❌ Must not produce ✅ — the risk is real and must be named
- ❌ Must not escalate to CRITICAL because "rate limiting is security-relevant" — it's a PITFALL, not an exploit

**Tone failures:**
- ❌ "You should not use in-memory storage" — it's labeled intentional; acknowledge the tradeoff
- ❌ Ignoring the `// MVP` comment and treating this as an oversight — the code demonstrates awareness
- ❌ Moralizing about the decision rather than naming the production consequence

**Generic output:**
- ❌ "Consider using Redis" — name when this breaks (any restart), not what to use
- ❌ `🧪` line that says "load test the endpoint" — must name the restart-resets-counter behavior
- ❌ Finding with no `file:line` pointing to the `new Map` declaration

**The key distinction this golden enforces:**
- An in-memory store with no comment → PITFALL (oversight)
- An in-memory store with an explicit MVP comment → still PITFALL (the risk is real), but ⚠️ not ❌
- VibeCheck names the risk without overriding the developer's judgment
