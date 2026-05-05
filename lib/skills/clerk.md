# Clerk Integration — VibeCheck Skill

This project uses Clerk for authentication. When reviewing auth-related code, apply these rules.

## Critical checks

**Middleware must cover protected routes**
Clerk middleware in `middleware.ts` (Next.js) must match every route that serves authenticated content. A common failure: `matcher` config that excludes API routes, or a `publicRoutes` list that accidentally includes `/api/user` or similar. Check the matcher against the actual route structure.

**`auth()` vs `currentUser()` — use the right one**
- `auth()` from `@clerk/nextjs/server` → fast, reads session from cookie, no network call. Use for auth checks (is the user signed in?).
- `currentUser()` → makes a network call to Clerk. Use only when you need user metadata (name, email, custom attributes). Never call it in middleware or in code that runs on every request.

**Server-side auth for server actions and API routes**
In Next.js App Router: `auth()` must be called inside the server action or route handler — not passed from a parent component. A `userId` passed as a prop from a client component is untrusted input.

## Common mistakes in this stack

- Calling `useAuth()` or `useUser()` in a Server Component — these are client hooks. Server components use `auth()` and `currentUser()` from `@clerk/nextjs/server`.
- Redirecting to `/sign-in` manually instead of using Clerk's `redirectToSignIn()` → Clerk's version preserves the return URL and handles SSO flows correctly.
- Not protecting the `/api/` directory in middleware → API routes are often missed because developers focus on page routes. Every `/api/` route that touches user data needs an auth check.
- Storing `userId` from Clerk in your own DB alongside Clerk's user object → you now have two sources of truth. Store only `clerkUserId` as the FK; fetch user metadata from Clerk when needed.

## What to read during review

1. `middleware.ts` — check the matcher covers all protected routes
2. Any server action (`"use server"`) that reads or writes user data — confirm `auth()` is called first
3. Any API route under `/api/` — same check
