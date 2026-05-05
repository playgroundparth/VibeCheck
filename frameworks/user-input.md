# Framework: User-Facing Input

**Trigger detection:** form handler, API endpoint receiving body/query params, file upload handler, search input, any function that reads from `req.body`, `req.query`, `req.params`, user-controlled fields.

**Questions to ask about the changed code:**

1. What input do you not trust? Which fields in this handler could a user set to arbitrary values? Are all of them validated before use?
2. What's the worst thing a user can do with this input? SQL injection, path traversal, SSRF, script injection, oversized payloads — which applies here?
3. Does the response include any data the caller didn't explicitly request? Are you returning full rows, internal IDs, or admin-only fields?
4. What happens with malicious but valid-looking input? Empty string, null, 0, negative number, string that looks like a number, unicode edge cases?
5. Is there a rate limit on this endpoint? What stops an attacker from calling this 10,000 times?
6. If this is a file upload: what file types are accepted? Is the type checked server-side (not just content-type header)? Where does the file land?

**Red flags (always call out):**
- User input interpolated into SQL, shell command, file path, or URL without sanitization
- Response that echoes user input back without encoding (XSS risk)
- No content-length check on uploads
- Validation only on the client (missing server-side equivalent)
- Returning the full user object when only the ID was needed
