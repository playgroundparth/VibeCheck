# Golden: Webhook Signature Bypass → CRITICAL

## Scenario

Developer adds a Stripe webhook handler. It processes payment events and updates subscription status in the DB. It does not verify the Stripe signature.

## What Changed

```
app/api/webhooks/stripe/route.ts   ← new file
```

## Evidence Files VibeCheck Should Read

From `project_map.json` → `api_routes` group or heuristic (webhook path):

```
app/api/webhooks/stripe/route.ts   ← the changed file itself
```

No cross-file evidence needed — the exploit is visible in the single file.

## Evidence Found

`app/api/webhooks/stripe/route.ts`:
```ts
export async function POST(req: Request) {
  const body = await req.json();          // ← raw body parsed, not raw buffer

  if (body.type === "customer.subscription.updated") {
    await db.subscription.update({
      where: { stripeId: body.data.object.id },
      data: { status: body.data.object.status },
    });
  }

  return NextResponse.json({ received: true });
}
```

No call to `stripe.webhooks.constructEvent()`. No `stripe-signature` header check.

## Expected VibeCheck Output

**Finding (evidence-anchored):**
```json
{
  "severity": "CRITICAL",
  "title": "Stripe webhook has no signature verification",
  "file": "app/api/webhooks/stripe/route.ts:2",
  "files_read": ["app/api/webhooks/stripe/route.ts"],
  "why": "Anyone can POST a forged event and upgrade their subscription to paid — no auth required"
}
```

**Footer:**
```
---
VibeCheck: ❌ Fix before shipping · 🔴 1 critical
🧪 Before shipping: send a forged POST to /api/webhooks/stripe with a fake subscription.updated payload — it should be rejected, not processed
💡 Stripe's constructEvent() throws on bad signatures — call it before touching body
```

## Global Invariant

- **verdict is present** — ❌ Fix before shipping
- **verdict answers "can I continue?"** — no, stop here

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce ⚠️ or ✅ — CRITICAL always escalates to ❌ Fix before shipping
- ❌ Must not downgrade to PITFALL because "it's not being exploited yet"

**Generic output:**
- ❌ "Consider adding signature verification" — name the exploit, not the suggestion
- ❌ "You may want to use constructEvent()" — state what happens without it
- ❌ `why` field that says "this is insecure" without describing the concrete attack
- ❌ No `file:line` pointing to the unverified `req.json()` call
- ❌ Finding that doesn't name which file was read (`files_read` missing)

**Wrong scope:**
- ❌ `🧪` line must describe sending a forged request, not "write a unit test for the handler"
- ❌ Must not flag missing tests as the primary issue when there's an active exploit
- ❌ Must not flag the `await` without try/catch — that's HYGIENE, and CRITICAL takes priority
