# Golden: Overengineered Custom Auth → PITFALL (REINVENTING)

## Scenario

Developer builds a custom JWT authentication system from scratch — manual token signing, rotation, blacklist. The project already has Supabase wired up, which provides auth out of the box.

## What Changed

```
lib/auth/jwt.ts          ← new file, custom JWT sign/verify
lib/auth/token-store.ts  ← new file, in-memory token blacklist
lib/auth/middleware.ts   ← new file, manual header extraction
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

export function verifyToken(token: string): object | null {
  // ... manual split and verify
}
```

`lib/auth/token-store.ts`:
```ts
const blacklist = new Set<string>();  // ← in-memory, lost on restart

export function revoke(token: string) { blacklist.add(token); }
export function isRevoked(token: string) { return blacklist.has(token); }
```

`package.json` already has `@supabase/supabase-js` installed. `lib/supabase.ts` exists.

## Expected VibeCheck Output

**Findings:**

```json
[
  {
    "severity": "PITFALL",
    "title": "Custom JWT implementation when Supabase auth is already installed",
    "file": "lib/auth/jwt.ts",
    "why": "Manual JWT is harder to audit, easier to get wrong, and duplicates what supabase.auth already does"
  },
  {
    "severity": "PITFALL",
    "title": "In-memory token blacklist lost on every server restart",
    "file": "lib/auth/token-store.ts:3",
    "why": "Revoked tokens become valid again after any deploy or crash — revocation silently stops working"
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

## What Must NOT Happen

- Must not produce ❌ Fix before shipping — no concrete exploit exists yet (though the in-memory blacklist is close)
- Must not say "this is good" or soften the reinvention concern
- Must not flag the crypto import as a security issue — it's not the problem
- Must identify BOTH issues (reinventing AND the in-memory blacklist), not just one
