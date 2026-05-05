# Golden: Safe MVP Shortcut → ✅ Safe to continue

## Scenario

Developer adds a simple utility to format currency values for display. No auth, no DB, no external calls. Pure functions with tests.

## What Changed

```
lib/format.ts         ← new file, formatCurrency() and formatDate()
lib/format.test.ts    ← new file, 4 unit tests
```

## Evidence Files VibeCheck Should Read

```
lib/format.ts         ← changed file (no cross-file evidence needed)
lib/format.test.ts    ← changed file
```

No `project_map.json` group matches pure utility files. No lifecycle check triggered.

## Evidence Found

`lib/format.ts`:
```ts
export function formatCurrency(amount: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(amount / 100);  // assumes cents
}
```

`lib/format.test.ts`:
```ts
test("formats cents as dollars", () => {
  expect(formatCurrency(1099)).toBe("$10.99");
});
test("handles zero", () => {
  expect(formatCurrency(0)).toBe("$0.00");
});
```

No user input flows. No network calls. No auth paths. Test file exists.

## Expected VibeCheck Output

**Findings:** none

**Footer:**
```
---
VibeCheck: ✅ Safe to continue
🧪 Before shipping: verify formatCurrency is called with cents everywhere — callers that pass dollar amounts will be off by 100x
```

## Global Invariant

- **verdict is present** — ✅ Safe to continue
- **verdict answers "can I continue?"** — yes

## What Must NOT Happen

**Wrong verdict:**
- ❌ Must not produce any finding — no risk surface
- ❌ Must not produce ⚠️ to seem cautious

**Generic output:**
- ❌ "Consider adding more tests" — a test file already exists
- ❌ "You may want to add input validation" — pure functions don't have user-facing endpoints
- ❌ "Add rate limiting" — there's no route here
- ❌ `🧪` line that says "run the test suite" — must name the actual risk (the cents assumption and caller consistency)
- ❌ Finding with no evidence — no file was read that contains a problem

**Wrong scope:**
- ❌ Must not flag console.log, naming conventions, or missing JSDoc
- ❌ Must not flag missing rate limiting on a utility function
- ❌ Must not manufacture a HYGIENE finding to appear thorough
