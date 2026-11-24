# Stage: Posts

Read `runs/<day>/understanding.md` and `runs/<day>/source.json`, then write `runs/<day>/posts.json`.

## Rules
- Output JSON with `title`, `source_url`, `thread` (3 to 8 posts), and `followups` (1 to 2 reply prompts).
- Each post object has `{"text": "...", "images": []}`.
- Every post must be at most 280 weighted characters (counting `{ARTICLE_URL}` as 23 chars).
- Include `{ARTICLE_URL}` in the final post of `thread`.
- No hype phrases, clickbait, or thread emojis.
- Attribute opinions to the author; never state opinions as settled fact.
