# Framework: Concurrent State Mutation

**Trigger detection:** counter, score, balance, inventory, like count, vote count, session data, rate limit tracker, queue depth, any value that multiple concurrent requests might read and write.

**Questions to ask about the changed code:**

1. What happens when two requests hit this simultaneously? Trace the read-modify-write cycle: if both reads happen before either write completes, does the second write overwrite the first?
2. Is the mutation atomic? (DB-level `INCREMENT`, a transaction, a compare-and-swap) Or is it a fetch-then-write that's vulnerable to the race?
3. If this is in-memory: what happens when the process restarts? Is that acceptable, or is the data supposed to survive?
4. If this is rate limiting: what happens with multiple server instances? Does each maintain its own counter, making the limit effectively multiplied by the number of instances?
5. What's the consequence of getting this wrong? A counter being off by one is different from a financial balance being wrong or a rate limit being bypassed.

**Red flags (always call out):**
- Read-then-write without a transaction or atomic update
- In-memory counter for anything that should survive restarts or work across instances
- Rate limiter using module-level variable in a serverless function
- Optimistic update without a conflict-detection mechanism
- Lock that's never released on error (deadlock waiting to happen)
