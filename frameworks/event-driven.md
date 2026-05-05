# Framework: Event-Driven

**Trigger detection:** webhook handler, queue consumer, pub/sub subscriber, event listener, message handler, `on('event', ...)` pattern, any function receiving a payload it didn't initiate.

**Questions to ask about the changed code:**

1. What happens when this event fires twice? Is the handler idempotent, or does duplicate delivery cause double-processing?
2. What happens when the handler crashes mid-execution? Does the event system retry? If so, does the handler handle partial completion?
3. What happens when the payload is malformed or missing expected fields? Does it fail loudly (error logged, event NACKed), or silently succeed (wrong state, no trace)?
4. Who verifies the event came from the expected source? Is there signature/HMAC verification before the payload is trusted?
5. What's the ordering guarantee? Does this handler assume events arrive in order? What breaks if they don't?
6. What's the visibility into failures? If this handler fails at 2am, who finds out, how fast, and how do they debug it?

**Red flags (always call out):**
- Handler returns 200 before completing work — queue thinks it succeeded, retries never fire
- No idempotency check on a write operation
- Payload trusted without origin verification
- No dead-letter queue or equivalent for failed events
- Logging that only fires on success, not failure
