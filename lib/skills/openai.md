# OpenAI / LLM Integration — VibeCheck Skill

This project calls an LLM API (OpenAI, Anthropic, or similar). When reviewing AI-related code, apply these rules.

## Critical checks

**API key never in client-side code**
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or any LLM provider key must not appear in:
- Browser bundles (Next.js `app/` components without `"use server"`)
- `NEXT_PUBLIC_` environment variables
- Any code imported by client components

If the key reaches the client, every user of the app can extract it and use your quota.

**Timeout configuration**
LLM calls regularly take 20–60 seconds. Without an explicit timeout, failed requests hang until the platform kills them (Vercel default: 10s). On serverless: set `maxDuration` on the route. In the SDK: set `timeout` in the options. On the client: show a loading state with a time limit and a "this is taking longer than expected" message.

## Common mistakes in this stack

- No streaming for long responses → users stare at a blank screen for 10+ seconds, then see the full response appear. Use the streaming API and flush tokens to the client as they arrive.
- No retry on transient errors → LLM APIs return 429 (rate limit) and 503 (overloaded) regularly. Add exponential backoff with 2-3 retries on these status codes. Don't retry on 4xx client errors.
- Passing user input directly to the prompt without sanitization → prompt injection. User writes "Ignore previous instructions and..." and your system prompt is bypassed. Validate and sanitize user content before concatenating into prompts.
- Storing full conversation history in memory → grows unbounded, eventually exceeds context window and crashes. Truncate to a sliding window, or store in DB and load only what fits.
- Not handling `finish_reason: "length"` → model hit the token limit mid-response. The output is incomplete. Check `finish_reason` and either retry with a summary or tell the user the response was truncated.

## What to read during review

1. The file that initializes the LLM client — confirm the key comes from env, not hardcoded
2. The route or function that makes the LLM call — check timeout and error handling
3. Any file that concatenates user input into a prompt — check for injection risk
