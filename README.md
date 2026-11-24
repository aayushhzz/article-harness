# Article-to-X Harness

A lightweight, stdlib-only workflow harness for turning high-signal Hacker News essays on AI and agentic engineering into grounded understanding notes and concise X threads.

The model reads and drafts; deterministic Python gates enforce source grounding, structure, X character limits, topic filtering, and deduplication.

## Structure

| Path | Role |
|---|---|
| `CONTRACT.md` | Checkable definition of done and non-negotiable constraints |
| `config.json` | Configurable topic filters, word bounds, X length limits, and banned phrases |
| `harness/article_harness.py` | CLI for HN fetch/filter, HTML text extraction, deterministic gates, preview rendering, and ledger recording |
| `prompts/` | Stage prompts (`select.md`, `understand.md`, `posts.md`, `review.md`) |
| `ARTICLE_LIST.json` | Ledger of posted and rejected articles to prevent duplicates |
| `PROGRESS.md` | Append-only progress log |
| `runs/` | Gitignored per-day run artifacts (`selection.json`, `source.html`, `source.json`, `understanding.md`, `posts.json`) |
| `tests/` | Unit tests covering extraction, filtering, gates, rendering, and ledger updates |

## Usage

Requires Python 3.10+ (standard library only, no third-party packages).

```bash
# 1. Fetch and filter top HN stories on AI / agentic engineering
python3 -m harness.article_harness fetch --day 2026-11-24

# 2. After writing runs/<day>/selection.json, validate selection
python3 -m harness.article_harness gate select --day 2026-11-24

# 3. Download and extract article text into runs/<day>/source.json
python3 -m harness.article_harness extract --day 2026-11-24
python3 -m harness.article_harness gate source --day 2026-11-24

# 4. After writing runs/<day>/understanding.md and posts.json, run gates
python3 -m harness.article_harness gate understand --day 2026-11-24
python3 -m harness.article_harness gate posts --day 2026-11-24

# 5. Preview the resolved thread (substitutes {ARTICLE_URL})
python3 -m harness.article_harness render --day 2026-11-24

# 6. Check overall run status
python3 -m harness.article_harness status --day 2026-11-24

# 7. Record outcome in ARTICLE_LIST.json and PROGRESS.md
python3 -m harness.article_harness record --day 2026-11-24 --status posted --thread-id 12345
python3 -m harness.article_harness record --day 2026-11-24 --status rejected --reason "promotional announcement"
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```
