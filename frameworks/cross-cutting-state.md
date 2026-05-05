# Framework: Cross-Cutting State

**Trigger detection:** auth context, feature flag, session, tenant/org context, request context passed through multiple layers, middleware that sets shared state, any value that flows implicitly across function boundaries rather than being passed explicitly.

**Questions to ask about the changed code:**

1. Is there any path where this context is missing or stale when downstream code assumes it's present? What's the fallback when the auth context is null, the feature flag is undefined, or the tenant is unset?
2. Is this state set once (request start) and read-only after, or can it be mutated mid-request? If mutable, who's allowed to mutate it?
3. Is this state scoped correctly to the request? Or could a previous request's state bleed into the next one (particularly in connection pools, worker threads, or module-level singletons)?
4. Is there a test that verifies the behavior when this state is missing? Auth middleware bugs are classic "works in dev, fails for unauthenticated users in prod" failures.
5. Are all consumers of this state protected if the upstream setter is removed or renamed? What breaks if the middleware is skipped?

**Red flags (always call out):**
- Auth or tenant context stored in a module-level variable (bleeds across requests)
- Feature flag read before it's guaranteed to be loaded
- Downstream code that assumes context is always set, with no fallback for unauthenticated paths
- Context that's set in one middleware but consumed in a route that doesn't run that middleware
- Silent default value when context is missing (returns "no feature" rather than erroring — can hide middleware ordering bugs)
