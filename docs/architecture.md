# article-harness Architecture

`article-harness` separates **generative work** (reading essays, drafting analysis, writing threads via the prompts in [`prompts/`](../prompts/)) from **deterministic enforcement** implemented in pure Python ([`harness/article_harness.py`](../harness/article_harness.py)).

## Design Principles

1. **Zero external dependencies**: Uses only `urllib.request`, `html.parser`, `json`, `re`, and `argparse` so it runs cleanly anywhere Python 3.10+ is installed.
2. **Contract-first gates**: Every stage produces a concrete file under `runs/<day>/` that must pass a deterministic check before advancing (see [`CONTRACT.md`](../CONTRACT.md)).
3. **Append-only state**: `ARTICLE_LIST.json` prevents re-covering previously posted or rejected HN item IDs, and `PROGRESS.md` records a UTC-timestamped audit trail.

## Deterministic Gates

| Gate | Target File | Checks Enforced |
|---|---|---|
| `select` | `runs/<day>/selection.json` | Required keys (`id`, `title`, `url`, `hn_url`), valid `http(s)://` URL, and `id` not already in `ARTICLE_LIST.json`. |
| `source` | `runs/<day>/source.json` | Non-empty extracted text and `word_count` within `[source.min_words, source.max_words]`. |
| `understand` | `runs/<day>/understanding.md` | Presence and non-empty body for every `## <Section>` listed in `config.json` (`Problem`, `Central point`, `Evidence`, `Limits and open questions`, `Angle`). |
| `posts` | `runs/<day>/posts.json` | Required metadata (`title`, `source_url`), thread/followup counts within bounds, no duplicate post text, X weighted character count (`weighted_len`, counting URLs and `{ARTICLE_URL}` as 23 chars) `<= 280`, at least one link/placeholder in the thread, and zero banned phrases/emojis. |

## HTML Extraction

`_ArticleHTMLParser` subclasses `html.parser.HTMLParser` to:
- Strip boilerplate subtrees (`script`, `style`, `noscript`, `svg`, `nav`, `footer`, `header`).
- Extract `<title>`, `<meta name="author">`, and publication date metadata.
- Preserve paragraph boundaries across block-level tags (`p`, `div`, `article`, `section`, `h1`–`h4`, `li`, `blockquote`, `pre`, `br`) and normalize whitespace.
- Support offline re-extraction via `extract --from-html` when `source.html` is already saved locally.
