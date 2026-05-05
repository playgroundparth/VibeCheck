# Golden: Unnecessary Abstraction → PITFALL (OVERBUILDING)

## Scenario

Developer wraps a single Prisma call in a service class with an interface, a factory, and dependency injection. The call is used in exactly one place. There is no test that required the abstraction, no second implementation planned, no injection needed at runtime.

## What Changed

```
lib/services/user-service.ts          ← new file, UserService class
lib/services/interfaces/IUserService.ts ← new file, interface
lib/services/factory.ts               ← new file, factory function
app/api/users/[id]/route.ts           ← modified, now uses factory()
```

## Evidence Found

`lib/services/user-service.ts`:
```ts
export class UserService implements IUserService {
  constructor(private db: PrismaClient) {}

  async getUser(id: string): Promise<User | null> {
    return this.db.user.findUnique({ where: { id } });
  }
}
```

`lib/services/factory.ts`:
```ts
import { PrismaClient } from "@prisma/client";
import { UserService } from "./user-service";

export function createUserService() {
  return new UserService(new PrismaClient());
}
```

`app/api/users/[id]/route.ts` (before and after):
```ts
// Before (3 lines):
const user = await db.user.findUnique({ where: { id: params.id } });

// After (uses service):
const svc = createUserService();
const user = await svc.getUser(params.id);
```

`IUserService.ts`: single method interface matching the one method on the class.

No tests use mocking. No second implementation exists or is planned.

## Expected VibeCheck Output

**Finding (evidence-anchored):**
```json
{
  "severity": "PITFALL",
  "title": "Service/interface/factory layer for a single Prisma findUnique call",
  "file": "lib/services/user-service.ts:1",
  "files_read": [
    "lib/services/user-service.ts",
    "lib/services/interfaces/IUserService.ts",
    "lib/services/factory.ts",
    "app/api/users/[id]/route.ts"
  ],
  "why": "3 new files to wrap 1 line — adds indirection with no payoff until there's a second implementation or a mock test, neither of which exists"
}
```

**Footer:**
```
---
VibeCheck: ⚠️ OK for MVP, not prod · ⚡ 1 pitfall
🧪 Before shipping: call the route and confirm it returns the right user — the extra factory call could instantiate a second PrismaClient and exhaust connections
💡 The abstraction is solving a future problem that hasn't arrived yet — inline the query until you have two implementations or a real test boundary
```

## Global Invariant

- **verdict is present** — ⚠️ OK for MVP, not prod
- **verdict answers "can I continue?"** — yes, but you're adding weight you'll have to carry

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce ✅ — the abstraction is real drag that will cost later
- ❌ Must not produce ❌ — no security issue, no data loss risk

**Generic output:**
- ❌ "Consider simplifying the abstraction" — state what the cost is
- ❌ "You may want to inline this" — make a statement, not a suggestion
- ❌ Finding with no `file:line` pointing to where the abstraction starts
- ❌ `files_read` missing — the finding is only valid if all four files were actually read
- ❌ Praising "good separation of concerns" in the same response

**Wrong scope:**
- ❌ Must not flag this as CRITICAL — it's drag, not an exploit
- ❌ Must not flag missing interface methods — the interface matches the class
- ❌ `🧪` line must be specific: the PrismaClient instantiation risk in the factory, not "test the endpoint"
