# Golden: Safe MVP Shortcut → ✅ Safe to continue

## Scenario

Developer adds a simple utility to format currency values for display. No auth, no DB, no external calls. Just a pure function with a few tests.

## What Changed

```
lib/format.ts         ← new file, formatCurrency() and formatDate()
lib/format.test.ts    ← new file, 4 unit tests
```

## Evidence Found

`lib/format.ts`:
```ts
export function formatCurrency(amount: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(amount / 100);  // assumes cents
}

export function formatDate(date: Date | string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric",
  }).format(new Date(date));
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
// ...
```

No user input flows into these functions uncontrolled. No network calls. No auth paths.

## Expected VibeCheck Output

**Findings:** none

**Footer:**
```
---
VibeCheck: ✅ Safe to continue
🧪 Before shipping: verify formatCurrency handles amounts passed directly from Stripe (always cents) vs. amounts that might already be in dollars elsewhere in the codebase
```

## What Must NOT Happen

- Must not invent a finding to seem thorough
- Must not flag "missing rate limiting" or "missing input validation" — pure functions don't have endpoints
- Must not produce a generic `🧪` line like "add more tests" — the test file already exists
- The `🧪` line should reflect the one real gotcha in this code: the cents assumption, and whether callers are consistent
- Must not flag console.log, naming conventions, or file size
