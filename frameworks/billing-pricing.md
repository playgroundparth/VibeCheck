# Framework: Billing / Pricing Change

**Trigger detection:** price, plan, subscription, tier, feature gate, quota, usage limit, trial, discount, coupon, any code that determines what a user can access or how much they pay.

**Questions to ask about the changed code:**

1. What happens to existing users when this change deploys? Do they get the new behavior automatically, or are they grandfathered on the old behavior?
2. Is there any path where a user gets charged the wrong amount — more or less than what they agreed to?
3. Is there idempotency on any charge or subscription update? What happens if the payment webhook fires twice?
4. What's the rollback story if this pricing logic is wrong? Can you flip a feature flag and revert without a deploy?
5. Does this change affect what's shown to users vs. what's actually enforced server-side? Are the UI labels and the enforcement in sync?
6. Are there any edge cases — free trial users, paused subscriptions, users mid-billing-cycle — that this logic doesn't handle correctly?

**Red flags (always call out):**
- Pricing logic only in the UI (enforced client-side, bypassable)
- Subscription check that doesn't handle expired, paused, or cancelled states
- Missing idempotency on charge or subscription create
- Feature gate that can be bypassed by downgrading then upgrading
- No audit log of plan changes
