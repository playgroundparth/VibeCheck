# Framework: External Service Call

**Trigger detection:** `fetch`, `axios`, `got`, HTTP client, SDK call to any third-party service (OpenAI, Stripe, Resend, Twilio, SendGrid, etc.), database call to an external host, `supabase.from(...)`, any call that crosses a network boundary.

**Questions to ask about the changed code:**

1. What happens when the service is down or slow? Is there a timeout? Does the caller get a sensible error, or does it hang?
2. What happens on a transient error (429, 503, network hiccup)? Is there retry logic with backoff? Or does one failure propagate to the user as a hard error?
3. Is the API key or credential coming from environment variables — not hardcoded, not in a client bundle?
4. What's the cost surface? If this is an LLM call or metered API, what's the worst-case cost if it's called in a loop or by an attacker? Is there a budget guard?
5. Is the response validated before it's used? What happens if the service returns an unexpected shape?
6. Is there a fallback if this service is unavailable? Or is this a hard dependency where unavailability means complete feature failure?

**Red flags (always call out):**
- No timeout on the call
- API key in source code or client-visible variable
- No retry on transient errors for user-critical paths
- LLM call in a loop with no ceiling on iterations or cost
- Response used directly without checking for error shape or null fields
