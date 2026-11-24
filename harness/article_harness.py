#!/usr/bin/env python3
"""Deterministic workflow harness for turning Hacker News AI/agentic essays into X threads.

Standard library only. Supports:
  - fetch:    Pull and filter top HN stories on AI/agentic engineering.
  - extract:  Download article HTML (or parse local source.html) into source.json.
  - gate:     Run deterministic checks on select, source, understand, or posts.
  - render:   Dry-run preview of posts.json with {ARTICLE_URL} substituted.
  - status:   Show artifact presence and gate results for a run day.
  - record:   Append a posted/rejected entry to ARTICLE_LIST.json and PROGRESS.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
URL_RE = re.compile(r"https?://\S+")
ARTICLE_URL_PLACEHOLDER = "{ARTICLE_URL}"


def load_config(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / "config.json").read_text(encoding="utf-8"))


def load_article_list(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / "ARTICLE_LIST.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_article_list(entries: list[dict[str, Any]], root: Path = ROOT) -> None:
    path = root / "ARTICLE_LIST.json"
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def append_progress(day: str, message: str, root: Path = ROOT) -> None:
    path = root / "PROGRESS.md"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    line = f"- {stamp} [{day}] {message}\n"
    if not path.exists():
        path.write_text("# Progress\n" + line, encoding="utf-8")
        return
    existing = path.read_text(encoding="utf-8")
    prefix = "" if existing.endswith("\n") or not existing else "\n"
    path.write_text(existing + prefix + line, encoding="utf-8")


def run_dir(day: str, root: Path = ROOT) -> Path:
    return root / "runs" / day


def today_str() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


# ---------- HTML extraction ----------

class _ArticleHTMLParser(HTMLParser):
    """Minimal stdlib HTML-to-text extractor focusing on readable paragraphs."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header"}
    BLOCK_TAGS = {"p", "div", "article", "section", "h1", "h2", "h3", "h4", "li", "blockquote", "pre", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.byline: str = ""
        self.published: str = ""
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").lower()
            content = attr_map.get("content", "").strip()
            if content:
                if name in {"author", "article:author"} and not self.byline:
                    self.byline = content
                elif name in {"article:published_time", "date", "pubdate"} and not self.published:
                    self.published = content
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS:
            self._chunks.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS:
            self._chunks.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip_depth > 0:
            return
        self._chunks.append(data)


def extract_article_from_html(raw_html: str, fallback_title: str = "") -> dict[str, Any]:
    parser = _ArticleHTMLParser()
    parser.feed(raw_html)
    parser.close()

    title = " ".join("".join(parser.title_parts).split()).strip() or fallback_title
    raw_text = html.unescape("".join(parser._chunks))
    paragraphs = [
        re.sub(r"[ \t]+", " ", block).strip()
        for block in re.split(r"\n{2,}", raw_text)
    ]
    clean_text = "\n\n".join(p for p in paragraphs if p)
    word_count = len(clean_text.split())
    return {
        "title": title,
        "byline": parser.byline,
        "published": parser.published,
        "word_count": word_count,
        "text": clean_text,
    }


# ---------- HN candidate filtering ----------

def filter_candidates(
    stories: list[dict[str, Any]],
    cfg: dict[str, Any],
    seen_ids: set[str],
) -> list[dict[str, Any]]:
    hn_cfg = cfg["hn"]
    min_score = int(hn_cfg.get("min_score", 50))
    topic_keywords = [k.lower() for k in hn_cfg.get("topic_keywords", [])]
    exclude_keywords = [k.lower() for k in hn_cfg.get("exclude_keywords", [])]

    selected: list[dict[str, Any]] = []
    for item in stories:
        if not item or item.get("type", "story") != "story":
            continue
        item_id = str(item.get("id", "")).strip()
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        score = int(item.get("score") or 0)
        if not item_id or not url or not title:
            continue
        if item_id in seen_ids:
            continue
        if score < min_score:
            continue

        haystack = title.lower()
        if any(bad in haystack for bad in exclude_keywords):
            continue
        if topic_keywords and not any(re.search(rf"\b{re.escape(kw)}\b", haystack) for kw in topic_keywords):
            continue

        selected.append(
            {
                "id": int(item_id) if item_id.isdigit() else item_id,
                "title": title,
                "url": url,
                "score": score,
                "comments": int(item.get("descendants") or 0),
                "by": item.get("by", ""),
                "hn_url": f"https://news.ycombinator.com/item?id={item_id}",
            }
        )

    selected.sort(key=lambda s: (s["score"], s["comments"]), reverse=True)
    return selected


def fetch_json(url: str, timeout: int = 15) -> Any:
    req = Request(url, headers={"User-Agent": "article-harness/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- deterministic gates ----------

def weighted_len(text: str, url_weight: int = 23) -> int:
    """Compute X character length treating URLs and {ARTICLE_URL} as url_weight."""
    total = len(text)
    if ARTICLE_URL_PLACEHOLDER in text:
        count = text.count(ARTICLE_URL_PLACEHOLDER)
        total += count * (url_weight - len(ARTICLE_URL_PLACEHOLDER))
    for match in URL_RE.finditer(text):
        total += url_weight - len(match.group(0))
    return total


def gate_select(day: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    sel_path = run_dir(day, root) / "selection.json"
    if not sel_path.exists():
        return [f"missing {sel_path}"]
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    for key in ("id", "title", "url", "hn_url"):
        if not str(sel.get(key, "")).strip():
            errors.append(f"selection.json missing required field '{key}'")
    url = str(sel.get("url", ""))
    if url and not url.startswith(("http://", "https://")):
        errors.append(f"selection.json url must start with http:// or https://: {url}")

    seen = {str(e.get("id")) for e in load_article_list(root)}
    sel_id = str(sel.get("id", "")).strip()
    if sel_id and sel_id in seen:
        errors.append(f"article id {sel_id} already exists in ARTICLE_LIST.json")
    return errors


def gate_source(day: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    cfg = load_config(root)
    src_path = run_dir(day, root) / "source.json"
    if not src_path.exists():
        return [f"missing {src_path}"]
    src = json.loads(src_path.read_text(encoding="utf-8"))
    text = (src.get("text") or "").strip()
    if not text:
        errors.append("source.json has empty 'text'")
    words = int(src.get("word_count") or len(text.split()))
    min_words = int(cfg["source"]["min_words"])
    max_words = int(cfg["source"]["max_words"])
    if words < min_words:
        errors.append(f"source word_count {words} < min_words {min_words}")
    if words > max_words:
        errors.append(f"source word_count {words} > max_words {max_words}")
    return errors


def gate_understand(day: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    cfg = load_config(root)
    und_path = run_dir(day, root) / "understanding.md"
    if not und_path.exists():
        return [f"missing {und_path}"]
    content = und_path.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()

    for req in cfg["understanding"]["required_sections"]:
        body = sections.get(req.lower(), "")
        if not body:
            errors.append(f"understanding.md missing or empty section '## {req}'")
    return errors


def gate_posts(day: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    cfg = load_config(root)
    posts_path = run_dir(day, root) / "posts.json"
    if not posts_path.exists():
        return [f"missing {posts_path}"]
    data = json.loads(posts_path.read_text(encoding="utf-8"))

    for key in ("title", "source_url"):
        if not str(data.get(key, "")).strip():
            errors.append(f"posts.json missing '{key}'")

    thread = data.get("thread")
    followups = data.get("followups")
    if not isinstance(thread, list):
        return errors + ["posts.json 'thread' must be a list"]
    if not isinstance(followups, list):
        return errors + ["posts.json 'followups' must be a list"]

    x_cfg = cfg["x"]
    if not (x_cfg["min_thread"] <= len(thread) <= x_cfg["max_thread"]):
        errors.append(
            f"thread length {len(thread)} outside [{x_cfg['min_thread']}, {x_cfg['max_thread']}]"
        )
    if not (x_cfg["min_followups"] <= len(followups) <= x_cfg["max_followups"]):
        errors.append(
            f"followups length {len(followups)} outside [{x_cfg['min_followups']}, {x_cfg['max_followups']}]"
        )

    banned = [p.lower() for p in cfg.get("banned_phrases", [])]
    url_weight = int(x_cfg["url_weight"])
    max_chars = int(x_cfg["max_chars"])

    has_link = False
    seen_texts: set[str] = set()
    for group_name, items in (("thread", thread), ("followups", followups)):
        for idx, item in enumerate(items, start=1):
            text = (item.get("text") if isinstance(item, dict) else "").strip()
            if not text:
                errors.append(f"{group_name}[{idx}] has empty text")
                continue
            norm = " ".join(text.lower().split())
            if norm in seen_texts:
                errors.append(f"{group_name}[{idx}] duplicates an earlier post")
            seen_texts.add(norm)

            wlen = weighted_len(text, url_weight=url_weight)
            if wlen > max_chars:
                errors.append(f"{group_name}[{idx}] length {wlen} > {max_chars}")

            if group_name == "thread" and (ARTICLE_URL_PLACEHOLDER in text or URL_RE.search(text)):
                has_link = True

            lowered = text.lower()
            for phrase in banned:
                if phrase in lowered:
                    errors.append(f"{group_name}[{idx}] contains banned phrase '{phrase}'")

    if not has_link:
        errors.append(f"thread must include {ARTICLE_URL_PLACEHOLDER} or a link to the article")
    return errors


GATES = {
    "select": gate_select,
    "source": gate_source,
    "understand": gate_understand,
    "posts": gate_posts,
}


# ---------- CLI commands ----------

def cmd_fetch(args: argparse.Namespace) -> int:
    cfg = load_config(ROOT)
    rd = run_dir(args.day, ROOT)
    rd.mkdir(parents=True, exist_ok=True)
    timeout = int(cfg["source"]["timeout_seconds"])
    top_ids = fetch_json(HN_TOP_URL, timeout=timeout)[: int(cfg["hn"]["top_limit"])]
    stories = [fetch_json(HN_ITEM_URL.format(item_id=i), timeout=timeout) for i in top_ids]
    seen_ids = {str(e.get("id")) for e in load_article_list(ROOT)}
    candidates = filter_candidates(stories, cfg, seen_ids)
    out_path = rd / "candidates.json"
    out_path.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
    append_progress(args.day, f"fetched {len(candidates)} candidate AI/agentic articles from HN", ROOT)
    print(f"wrote {len(candidates)} candidates to {out_path}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cfg = load_config(ROOT)
    rd = run_dir(args.day, ROOT)
    sel = json.loads((rd / "selection.json").read_text(encoding="utf-8"))
    html_path = rd / "source.html"
    if args.from_html:
        raw_html = html_path.read_text(encoding="utf-8")
    else:
        req = Request(sel["url"], headers={"User-Agent": "article-harness/1.0"})
        with urlopen(req, timeout=int(cfg["source"]["timeout_seconds"])) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")
        html_path.write_text(raw_html, encoding="utf-8")

    extracted = extract_article_from_html(raw_html, fallback_title=sel.get("title", ""))
    out_path = rd / "source.json"
    out_path.write_text(json.dumps(extracted, indent=2) + "\n", encoding="utf-8")
    append_progress(args.day, f"extracted article text ({extracted['word_count']} words)", ROOT)
    print(f"extracted {extracted['word_count']} words to {out_path}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    errors = GATES[args.stage](args.day, ROOT)
    if errors:
        print(f"FAIL [{args.stage}]:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"PASS [{args.stage}] for {args.day}")
    return 0


def render_posts(day: str, root: Path = ROOT) -> str:
    posts_path = run_dir(day, root) / "posts.json"
    data = json.loads(posts_path.read_text(encoding="utf-8"))
    url = data["source_url"]
    lines = [f"# {data['title']}", f"Source: {url}", "", "## Thread"]
    for i, item in enumerate(data["thread"], start=1):
        resolved = item["text"].replace(ARTICLE_URL_PLACEHOLDER, url)
        lines.append(f"{i}. {resolved}")
    lines.append("")
    lines.append("## Follow-ups")
    for i, item in enumerate(data["followups"], start=1):
        resolved = item["text"].replace(ARTICLE_URL_PLACEHOLDER, url)
        lines.append(f"{i}. {resolved}")
    return "\n".join(lines)


def cmd_render(args: argparse.Namespace) -> int:
    print(render_posts(args.day, ROOT))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    rd = run_dir(args.day, ROOT)
    print(f"Run: {args.day} ({rd})")
    for stage, fn in GATES.items():
        errs = fn(args.day, ROOT)
        mark = "PASS" if not errs else f"FAIL ({len(errs)} issue(s))"
        print(f"  - {stage:10s}: {mark}")
    return 0


def record_outcome(
    day: str,
    status: str,
    reason: str = "",
    thread_id: str = "",
    followup_id: str = "",
    x_handle: str = "",
    root: Path = ROOT,
) -> dict[str, Any]:
    sel = json.loads((run_dir(day, root) / "selection.json").read_text(encoding="utf-8"))
    entries = load_article_list(root)
    sel_id = str(sel["id"])
    if any(str(e.get("id")) == sel_id for e in entries):
        raise ValueError(f"article id {sel_id} is already recorded in ARTICLE_LIST.json")

    entry: dict[str, Any] = {
        "id": sel_id,
        "title": sel["title"],
        "url": sel["url"],
        "day": day,
        "status": status,
    }
    if status == "rejected" and reason:
        entry["reason"] = reason
    if status == "posted":
        x_ids: dict[str, str] = {}
        if thread_id:
            x_ids["thread1"] = thread_id
        if followup_id:
            x_ids["followup1"] = followup_id
        if x_ids:
            entry["x_ids"] = x_ids
        if x_handle:
            entry["x_handle"] = x_handle

    entries.append(entry)
    save_article_list(entries, root)
    note = f"recorded {status}: {sel['title']}" + (f" ({reason})" if reason else "")
    append_progress(day, note, root)
    return entry


def cmd_record(args: argparse.Namespace) -> int:
    entry = record_outcome(
        day=args.day,
        status=args.status,
        reason=args.reason or "",
        thread_id=args.thread_id or "",
        followup_id=args.followup_id or "",
        x_handle=args.x_handle or "",
        root=ROOT,
    )
    print(json.dumps(entry, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Article-to-X workflow harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Fetch and filter top HN stories")
    p_fetch.add_argument("--day", default=today_str())
    p_fetch.set_defaults(func=cmd_fetch)

    p_ext = sub.add_parser("extract", help="Download and extract article text")
    p_ext.add_argument("--day", default=today_str())
    p_ext.add_argument("--from-html", action="store_true", help="Read existing runs/<day>/source.html")
    p_ext.set_defaults(func=cmd_extract)

    p_gate = sub.add_parser("gate", help="Run a deterministic gate")
    p_gate.add_argument("stage", choices=list(GATES))
    p_gate.add_argument("--day", default=today_str())
    p_gate.set_defaults(func=cmd_gate)

    p_ren = sub.add_parser("render", help="Preview thread with {ARTICLE_URL} resolved")
    p_ren.add_argument("--day", default=today_str())
    p_ren.set_defaults(func=cmd_render)

    p_st = sub.add_parser("status", help="Show gate status for a run")
    p_st.add_argument("--day", default=today_str())
    p_st.set_defaults(func=cmd_status)

    p_rec = sub.add_parser("record", help="Record posted/rejected outcome to ARTICLE_LIST.json")
    p_rec.add_argument("--day", default=today_str())
    p_rec.add_argument("--status", choices=["posted", "rejected"], required=True)
    p_rec.add_argument("--reason", default="")
    p_rec.add_argument("--thread-id", default="")
    p_rec.add_argument("--followup-id", default="")
    p_rec.add_argument("--x-handle", default="")
    p_rec.set_defaults(func=cmd_record)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
