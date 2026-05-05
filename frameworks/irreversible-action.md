# Framework: Irreversible Action

**Trigger detection:** delete, drop, truncate, send (email, SMS, push notification), charge, refund, cancel subscription, revoke access, publish, deploy, any action that can't be cleanly undone.

**Questions to ask about the changed code:**

1. Is there a confirmation step before this action executes? Or can it trigger on a single unconfirmed call?
2. Is there a dry-run or preview mode? Can you see what *would* happen before committing?
3. What's the rollback story? If this runs with wrong inputs, what's the fastest path to recovery?
4. Is this action logged before it executes, not just after? (If it fails mid-way, you need a record of what was attempted.)
5. Is there authorization on top of authentication? Not just "is the user logged in" but "does this specific user have permission to delete this specific thing"?
6. For external sends (email, notification): is there a deduplication guard? Can this send the same message to the same user twice?

**Red flags (always call out):**
- Delete without a soft-delete or archive step (no recovery path)
- Email/SMS send without idempotency check (same trigger = duplicate send)
- Bulk operation (delete all where X) without a row count confirmation
- Missing authorization check for ownership (user A can delete user B's data)
- No audit log entry before execution
