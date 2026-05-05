# Supabase Integration — VibeCheck Skill

This project uses Supabase. When reviewing database or auth code, apply these rules.

## Critical checks

**Service role key in client-facing code**
`SUPABASE_SERVICE_ROLE_KEY` bypasses all Row Level Security. If it appears in any file that runs in a browser, in a Next.js route without auth verification, or is assigned to a variable named `supabaseAdmin` used in a public endpoint — that's a full RLS bypass. Callers get admin-level DB access with no restrictions.

Only use `service_role` in: server-only admin operations, seed scripts, or background jobs that never touch per-user data.

**RLS disabled on user tables**
Any table storing per-user data (profiles, posts, settings, etc.) needs RLS enabled AND policies that gate on `auth.uid()`. If RLS is disabled and you're using the anon key, every authenticated user can read every other user's rows.

Quick check: `select relname, relrowsecurity from pg_class where relname = 'your_table'` — `relrowsecurity` must be `true`.

**Anon key on the client is intentional, service key is not**
`NEXT_PUBLIC_SUPABASE_ANON_KEY` is safe to expose — it's designed for client use. `SUPABASE_SERVICE_ROLE_KEY` is not. If you see the service key in a `NEXT_PUBLIC_` variable, that's a showstopper.

## Common mistakes in this stack

- Using `supabase.auth.getUser()` on the server instead of `supabase.auth.getSession()` → `getSession()` is fast (reads cookie), `getUser()` makes a network call to Supabase on every request. Use `getUser()` only when you need verified user data (e.g., before writes).
- Not awaiting `supabase.from(...).select()` — Supabase client calls return a `PostgrestResponse`, not a Promise by default. Missing `await` gives you the builder object, not the data. Errors are silent.
- Calling Supabase in a React `useEffect` without cleanup → on fast navigation, the component unmounts before the query resolves, and the state setter runs on an unmounted component. Use `AbortController` or a `cancelled` flag.

## What to read during review

1. The Supabase client initialization (where `createClient` is called — verify which key is used)
2. Any server action or API route that accesses Supabase — confirm auth check happens before data fetch
3. Database migration files if schema changed
