# Contract: Hacker News AI/Agentic Article to X Thread

## Goal
Turn a high-signal Hacker News essay or engineering article about AI or agentic engineering into a structured understanding note and a concise, accurate X thread with 1–2 follow-up discussion prompts.

## Per-Run Artifacts (`runs/<day>/`)
- `candidates.json`: filtered Hacker News candidates (optional if selected manually)
- `selection.json`: chosen article metadata (`id`, `title`, `url`, `score`, `comments`, `by`, `hn_url`)
- `source.html`: raw downloaded article HTML
- `source.json`: extracted plain text, title, byline, and word count
- `understanding.md`: structured breakdown (`Problem`, `Central point`, `Evidence`, `Limits and open questions`, `Angle`)
- `posts.json`: X thread (`thread`) and reply prompts (`followups`), referencing `{ARTICLE_URL}`

## Persistent Ledger
- `ARTICLE_LIST.json`: append-only ledger of every posted or rejected article (`id`, `title`, `url`, `day`, `status`)
- `PROGRESS.md`: append-only timestamped log of run progress and review rounds

## Done When (All True)
1. `select` gate passes: `selection.json` has required fields and `id` is not already recorded in `ARTICLE_LIST.json`.
2. `source` gate passes: `source.json` has extracted text with at least `source.min_words` words.
3. `understand` gate passes: `understanding.md` includes all required sections with non-empty content, separating author claims from evidence.
4. `posts` gate passes:
   - Thread length is within `[min_thread, max_thread]` and follow-ups within `[min_followups, max_followups]`.
   - Every post is within `x.max_chars` (280) weighted characters (URLs and `{ARTICLE_URL}` count as `x.url_weight = 23`).
   - `{ARTICLE_URL}` appears in the thread.
   - No banned hype phrases or thread-bait emojis.
5. Human review approves the rendered thread before posting.
6. Outcome (posted or rejected) is recorded in `ARTICLE_LIST.json` and `PROGRESS.md`.

## Never
- Select promotional product announcements or off-topic posts outside AI / agentic engineering.
- Invent claims, numbers, or quotes not present in `source.json`.
- Store API keys, cookies, or personal credentials in repository files.
