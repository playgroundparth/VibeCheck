# Golden: Webhook Signature Bypass → CRITICAL

## Scenario

Developer adds a Stripe webhook handler. It processes payment events and updates subscription status in the DB. It does not verify the Stripe signature.

## What Changed

```
app/api/webhooks/stripe/route.ts   ← new file
```

## Evidence Found

`app/api/webhooks/stripe/route.ts`:
```ts
export async function POST(req: Request) {
  const body = await req.json();          // ← raw body parsed, not raw buffer
  
  // Handle different event types
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

**Finding:**
```json
{
  "severity": "CRITICAL",
  "title": "Stripe webhook has no signature verification",
  "file": "app/api/webhooks/stripe/route.ts:4",
  "why": "Anyone can POST a forged event and escalate their subscription to paid — no auth required"
}
```

**Footer:**
```
---
VibeCheck: ❌ Fix before shipping · 🔴 1 critical
🧪 Before shipping: send a forged POST to /api/webhooks/stripe with a fake subscription.updated event — it should be rejected, not processed
💡 Stripe's constructEvent() throws if the signature is wrong — use it before touching body
```

## What Must NOT Happen

- Must not produce ⚠️ or ✅ — CRITICAL always → ❌ Fix before shipping
- Must not say "consider adding signature verification" — state the exploit concretely
- Must not flag missing tests as the primary issue when there's an active exploit
- The `🧪` line must describe sending a forged request, not "write a unit test"
