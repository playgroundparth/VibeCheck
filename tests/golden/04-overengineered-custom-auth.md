# Golden: Overengineered Custom Auth → PITFALL (REINVENTING)

## Scenario

Developer builds a custom JWT authentication system from scratch — manual token signing, rotation, blacklist. The project already has Supabase wired up, which provides auth out of the box.

## What Changed

```
lib/auth/jwt.ts          ← new file, custom JWT sign/verify
lib/auth/token-store.ts  ← new file, in-memory token blacklist
lib/auth/middleware.ts   ← new file, manual header extraction
```

## Evidence Files VibeCheck Should Read

```
lib/auth/jwt.ts           ← changed file
lib/auth/token-store.ts   ← changed file
lib/supabase.ts           ← cross-file: Supabase already installed
package.json              ← cross-file: @supabase/supabase-js in dependencies
```

## Evidence Found

`lib/auth/jwt.ts`:
```ts
import crypto from "crypto";
const SECRET = process.env.JWT_SECRET!;

export function signToken(payload: object): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(payload));
  const sig = crypto.createHmac("sha256", SECRET)
    .update(`${header}.${body}`).digest("base64url");
  return `${header}.${body}.${sig}`;
}
```

`lib/auth/token-store.ts`:
```ts
const blacklist = new Set<string>();  // ← in-memory, lost on restart
export function revoke(token: string) { blacklist.add(token); }
```

`package.json`: `@supabase/supabase-js` is present.
`lib/supabase.ts`: exists and exports a configured client.

## Expected VibeCheck Output

**Findings (evidence-anchored):**
```json
[
  {
    "severity": "PITFALL",
    "title": "Custom JWT implementation when Supabase auth is already installed",
    "file": "lib/auth/jwt.ts:1",
    "files_read": ["lib/auth/jwt.ts", "lib/supabase.ts", "package.json"],
    "why": "Manual JWT is harder to audit and duplicates what supabase.auth already handles — two auth systems to maintain"
  },
  {
    "severity": "PITFALL",
    "title": "In-memory token blacklist is lost on every server restart",
    "file": "lib/auth/token-store.ts:1",
    "files_read": ["lib/auth/token-store.ts"],
    "why": "Revoked tokens become valid again after any deploy or crash — logout silently stops working in production"
  }
]
```

**Footer:**
```
---
VibeCheck: ⚠️ OK for MVP, not prod · ⚡ 2 pitfalls
🧪 Before shipping: restart the server after revoking a token and verify it's still rejected
💡 Supabase auth handles JWT, sessions, and revocation — three new files of custom auth is the kind of work that bites you at 2am
```

## Global Invariant

- **verdict is present** — ⚠️ OK for MVP, not prod
- **verdict answers "can I continue?"** — yes for now, but this accrues debt fast

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce ❌ Fix before shipping — no concrete exploit exists yet (the blacklist gap is close, but not a live exploit without an active revocation flow)
- ❌ Must not produce ✅ — two PITFALLs are present

**Generic output:**
- ❌ "Consider using Supabase auth instead" — state why this will hurt, not what to consider
- ❌ "You may want to persist the blacklist" — state what breaks when you don't
- ❌ Finding with no `file:line` reference to the in-memory blacklist line
- ❌ Finding that doesn't name `lib/supabase.ts` as the evidence that Supabase is available (`files_read` missing)

**Wrong scope:**
- ❌ Must not flag the `crypto` import as a security issue — it's not the problem
- ❌ Must identify BOTH issues separately, not collapse into one finding
- ❌ Must not praise the code structure while flagging the architecture
