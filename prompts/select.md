# Stage: Select

Pick one Hacker News essay or engineering write-up from `runs/<day>/candidates.json`.

## Rules
- Focus strictly on AI, LLMs, or agentic engineering.
- Exclude promotional product announcements, fundraising posts, and hiring threads.
- Never select an article ID already present in `ARTICLE_LIST.json`.
- Write the chosen item to `runs/<day>/selection.json` with `id`, `title`, `url`, `score`, `comments`, `by`, and `hn_url`.
