# Vercel Deployment — VibeCheck Skill

This project deploys to Vercel. When reviewing deployment-related code, apply these rules.

## Critical checks

**Environment variables must be in Vercel dashboard**
Any `process.env.VAR` used in server code must be added to the Vercel project's environment variables (not just `.env.local`). `.env.local` is never deployed. If a new env var appears in code, it needs to be added to Vercel before shipping.

Check: compare `.env.example` against Vercel dashboard. Every non-`NEXT_PUBLIC_` variable that your server uses must be there.

**`maxDuration` for slow routes**
Vercel Hobby: 10s limit. Vercel Pro: up to 300s (5 min). Default is 10s for all plans. Any route calling an LLM API, processing uploads, or doing heavy computation needs `export const maxDuration = N` at the top of the route file. Without it, the function silently times out and the user gets a 504.

**Edge Runtime limitations**
If a route uses `export const runtime = 'edge'`: no Node.js APIs (no `fs`, no `crypto.randomBytes`, no `Buffer`), no Prisma (unless using the edge adapter), no large dependencies. If any of these appear in an edge route, it will fail at runtime — not at build time.

## Common mistakes in this stack

- Using `fs` or Node.js built-ins in a route that runs on Edge — fails silently in dev (runs on Node.js locally), crashes in prod.
- Not setting `NEXTAUTH_URL` or equivalent for auth callbacks → works in local dev, breaks in production because the callback URL defaults to `localhost`.
- Cron jobs via Vercel Cron without idempotency → Vercel guarantees at-least-once delivery. If the cron handler does anything stateful (send email, charge, update), it needs a guard against double-execution.
- Large images in `/public` checked into git → Vercel has a deployment size limit. Use Vercel Image Optimization or an external CDN for images > 1MB.

## What to read during review

1. `vercel.json` if it exists — check cron schedules and function configs
2. Any route file that calls external services — check for `maxDuration`
3. Any route with `runtime = 'edge'` — verify no Node.js APIs are used
4. `.env.example` vs code — flag any env vars used in code but not in the example file
