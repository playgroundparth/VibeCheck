# Framework: User-Generated Content

**Trigger detection:** post, comment, review, message, upload, profile field, any content created by a user that other users can see or that the system stores and renders.

**Questions to ask about the changed code:**

1. Is user content encoded before it's rendered? What prevents XSS if a user puts `<script>` in their bio or comment?
2. Is there a content length limit? What prevents a user from submitting a 100MB string and degrading the DB or the render path?
3. What's the moderation story? If a user posts something illegal or abusive, is there a flag/report mechanism? A way to remove it quickly?
4. What's stored vs. what's rendered? If you're storing markdown or HTML, are you sanitizing on store, on render, or both?
5. If content is user-uploaded media: is the file type verified server-side? Where does it land? Is the serving URL guessable by other users?
6. Is the content attribution correct? Can user A post content that appears to come from user B?

**Red flags (always call out):**
- Rendering raw HTML from user input without sanitization
- No content length limit in the API or DB schema
- Storing content and rendering content in different encoding/sanitization paths (inconsistency = gap)
- Uploaded files served from the same domain as the app (XSS via SVG or HTML uploads)
- No rate limit on content creation (spam/abuse vector)
