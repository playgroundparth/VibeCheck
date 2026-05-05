# Prisma Integration — VibeCheck Skill

This project uses Prisma. When reviewing database code, apply these rules.

## Critical checks

**Schema change without migration**
If `schema.prisma` changed this turn and there's no new file in `prisma/migrations/`, the schema is out of sync with every deployed environment. This is a showstopper — works locally, fails everywhere else.

Correct flow: change schema → `npx prisma migrate dev --name description` → commit both schema and migration together.

**PrismaClient in serverless without connection pooling**
Each serverless invocation creates a new PrismaClient, which opens a DB connection. Under load, you exhaust the connection limit and requests fail. In Next.js / Vercel / AWS Lambda:
- Use Prisma Accelerate (drop-in, adds connection pooling + edge cache)
- Or use `@prisma/adapter-neon` for Neon serverless
- Or instantiate as a singleton with `global.prisma` guard

The singleton pattern: `const prisma = global.prisma || new PrismaClient(); if (process.env.NODE_ENV !== 'production') global.prisma = prisma;`

**Read-then-write without transaction**
Pattern: `findUnique` → modify value → `update`. Two concurrent requests read the same value, last write wins — first modification is silently lost. For counters, likes, inventory: use `increment`/`decrement` in `update`, or wrap in `$transaction`.

## Common mistakes in this stack

- Using `include: true` instead of explicit field selection → returns full rows including fields the client shouldn't see (internal flags, foreign keys, soft-delete markers). Always select by name.
- Not handling `P2025` (record not found) → `update` and `delete` throw `P2025` if the record doesn't exist. Unhandled, this crashes the process in serverless.
- N+1: querying inside a loop. Prisma makes this easy to write by accident. Use `include` or a batch `findMany` with `where: { id: { in: ids } }`.
- `$executeRaw` with string interpolation → SQL injection. Use `$queryRaw` with template literals (tagged): `` prisma.$queryRaw`SELECT * FROM users WHERE id = ${userId}` `` — this uses parameterized queries.

## What to read during review

1. `prisma/schema.prisma` — if it changed, check for a matching migration
2. The DB client initialization file — check for the singleton pattern in serverless
3. Any loop that contains a Prisma query — check for N+1
