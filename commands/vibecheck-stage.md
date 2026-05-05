# /vibecheck-stage

Sets the project stage so VibeCheck adjusts severity thresholds to match your current risk tolerance.

## Usage

```
/vibecheck-stage mvp
/vibecheck-stage growth
/vibecheck-stage prod
```

No argument → shows the current stage and what each stage means.

## What to do

1. Read the argument (mvp, growth, or prod). If no argument, read `.vibecheck/memory.json` to get the current stage (key: `project_stage`) and show the stage summary below, then stop.

2. Validate: only `mvp`, `growth`, or `prod` are valid. If something else: say so and list the valid options.

3. Read `.vibecheck/config.json`. Set `project_stage` to the new value. Write it back.

4. Read `.vibecheck/memory.json`. Set `project_stage` to the same value. Write it back. This is what the inline review layer reads — without this step, the inline check won't see the new stage.

5. Output the stage summary for the new stage (below).

6. Say: "Stage updated. Takes effect on your next file change — no restart needed."

---

## Stage summaries

### mvp
You're building fast. VibeCheck watches for real blockers and ignores engineering purism.

**Escalated to PITFALL** (things that will actually bite you at MVP scale):
- ARCH-05: Overbuilding — microservices, event buses, distributed patterns for a project with < 5 users. This adds ops complexity you can't afford to debug.
- AUTH-04: Auth check after data fetch — even MVPs get probed.

**Stays GOOD_TO_HAVE** (won't block you):
- DATA-07: Storing derived data — you'll fix it when it bites you, and it won't for a while.
- OPS-03: No retry on external API calls — occasional failures are acceptable during validation.
- OPS-04: Missing error boundary — real users aren't here yet.
- OPS-05: Missing health check endpoint.

**Still CRITICAL** (non-negotiable even for MVPs):
- Hardcoded secrets
- Webhook endpoints without signature verification
- Service-role key in public routes

---

### growth
You have real users. Reliability and security matter. Engineering quality is a means, not an end.

All pattern severities at their documented defaults. No escalation, no relaxation.

---

### prod
You're in production with SLAs or payments or data you can't afford to lose. VibeCheck tightens the screws.

**Escalated to CRITICAL** (must fix before the next deploy):
- DATA-01: In-memory rate limiter or counter — resets on every deploy or restart, limits become worthless.
- DATA-08: No DB connection pooling in serverless — under real load, you exhaust the connection limit.

**Escalated to PITFALL** (immediate ops risk):
- OPS-01: Env var not in deployment config — undefined in prod means broken feature.
- OPS-06: No timeout on LLM routes — users will hit gateway errors in prod traffic.

**Stays HYGIENE** (important but not deploy-blocking):
- DATA-03: Missing try/catch in payment paths — log and handle, but don't block the deploy.

---

## Notes

The stage affects how the inline review layer and `/vibecheck-review` interpret severity. It does not change what gets flagged — it changes what severity label is applied.

If you're unsure: start with `mvp`, move to `growth` when you have your first paying user, move to `prod` when you have an SLA or payments that can go wrong.
