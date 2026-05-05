# Stripe Integration — VibeCheck Skill

This project uses Stripe. When reviewing payment-related code, apply these rules in addition to the standard anti-pattern catalog.

## Critical checks

**Webhook signature verification**
Every webhook endpoint must call `stripe.webhooks.constructEvent(rawBody, sig, secret)` before touching the payload. If `req.json()` or `JSON.parse(body)` is called first, the signature check is bypassed. Stripe retries on non-2xx — without verification, any server can forge events.

Webhook handler in this project: `{{stripe_webhook_path}}`

**Idempotency on payment events**
Stripe retries webhooks. `payment_intent.succeeded`, `checkout.session.completed`, and `invoice.paid` handlers must check if `event.id` was already processed. Store processed IDs with a unique constraint. Missing this = double fulfillment on transient failures.

**Secret key on the server only**
`STRIPE_SECRET_KEY` (sk_live_*, sk_test_*) must never appear in client-side bundles. Check for it in Next.js `app/` (not `app/api/`), in any `export const` that gets tree-shaken to the client, or in `.env.local` next to `NEXT_PUBLIC_` variables.

**Publishable key is public, secret key is not**
Using `STRIPE_SECRET_KEY` in a route that doesn't require auth = anyone can trigger charges. The Stripe client initialized with the secret key must only run after auth is confirmed.

## Common mistakes in this stack

- Constructing `PaymentIntent` without idempotency key → duplicate charges on network retries. Use `stripe.paymentIntents.create({ ..., idempotencyKey: uniqueId })`.
- Catching Stripe errors with a bare `catch` and returning 500 → Stripe retries on 5xx, turning transient errors into loops. Return 200 after logging, use a dead-letter queue for real failures.
- Checking `event.type` without handling `charge.dispute.created` → disputes happen silently, you lose automatically if you don't respond within 7 days.

## What to read during review

1. The webhook handler file
2. The Stripe client initialization (where `new Stripe(key)` is called)
3. The env file or env validation schema — confirm `STRIPE_SECRET_KEY` is server-only, `STRIPE_PUBLISHABLE_KEY` is the one going to the client
