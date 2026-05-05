# Framework: Async / Scheduled Work

**Trigger detection:** cron job, background job, `setTimeout`/`setInterval`, queue worker, `async` function that runs outside a request/response cycle, scheduled function, `inngest`, `bullmq`, Vercel Cron, `node-cron`.

**Questions to ask about the changed code:**

1. What happens if the process dies mid-execution? Is the work atomic, or can it leave the system in a half-done state? Is there a cleanup or compensation path?
2. What happens if the job runs twice concurrently? (This is common on deploy, restart, or if the scheduler fires before the previous run completes.) Is there a lock or idempotency guard?
3. What happens if this job silently fails? Who finds out? Is there an alert, a log entry at ERROR level, a dead-letter queue, a retry count visible somewhere?
4. What's the expected runtime? What happens if it takes 10× longer than expected? Is there a timeout?
5. If this job mutates data: is there a way to revert if it runs with bad inputs?
6. What's the visibility on this job in production? Can you see at a glance whether it ran, when it last succeeded, and how long it took?

**Red flags (always call out):**
- No lock or guard against concurrent execution
- Errors caught and swallowed without logging or alerting
- Job that emails, charges, or sends external requests with no idempotency check
- No timeout — job can run forever and starve other work
- Scheduled task with no monitoring or visibility
