"""Unit tests for the article-harness deterministic workflow."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from harness import article_harness as ah


class ArticleHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="article-harness-test-"))
        shutil.copy(ah.ROOT / "config.json", self.tmp / "config.json")
        (self.tmp / "ARTICLE_LIST.json").write_text("[]\n", encoding="utf-8")
        (self.tmp / "PROGRESS.md").write_text("# Progress\n", encoding="utf-8")
        self.day = "2026-11-25"
        self.rd = self.tmp / "runs" / self.day
        self.rd.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_valid_run(self) -> None:
        (self.rd / "selection.json").write_text(
            json.dumps(
                {
                    "id": 999999,
                    "title": "Why coding agents need deterministic gates",
                    "url": "https://example.com/agent-gates",
                    "score": 320,
                    "comments": 140,
                    "by": "builder",
                    "hn_url": "https://news.ycombinator.com/item?id=999999",
                }
            ),
            encoding="utf-8",
        )
        words = " ".join(["agent"] * 260)
        (self.rd / "source.json").write_text(
            json.dumps(
                {
                    "title": "Why coding agents need deterministic gates",
                    "byline": "Jane Doe",
                    "published": "2026-11-25",
                    "word_count": 260,
                    "text": words,
                }
            ),
            encoding="utf-8",
        )
        (self.rd / "understanding.md").write_text(
            "# Understanding\n\n"
            "## Problem\nAgents drift without hard checks.\n\n"
            "## Central point\nPut verification in code, not prose.\n\n"
            "## Evidence\nBenchmark runs on 40 repos.\n\n"
            "## Limits and open questions\nDoes not cover UI tasks.\n\n"
            "## Angle\nPrompts ask; gates enforce.\n",
            encoding="utf-8",
        )
        (self.rd / "posts.json").write_text(
            json.dumps(
                {
                    "title": "Why coding agents need deterministic gates",
                    "source_url": "https://example.com/agent-gates",
                    "thread": [
                        {"text": "Prompt instructions alone rarely stop agent drift on multi-step edits.", "images": []},
                        {"text": "Moving length, schema, and test checks into code catches regressions early.", "images": []},
                        {"text": "Read the full write-up: {ARTICLE_URL}", "images": []},
                    ],
                    "followups": [
                        {"text": "Which deterministic gate saves you the most review time?", "images": []},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_extract_article_from_html_strips_scripts_and_nav(self) -> None:
        raw = """
        <html>
          <head>
            <title>Agent Harnesses</title>
            <meta name="author" content="Alex Builder">
            <style>body { color: red; }</style>
          </head>
          <body>
            <nav>Home About</nav>
            <article>
              <h1>Agent Harnesses</h1>
              <p>Deterministic gates keep LLM workflows reliable.</p>
              <script>console.log("ignore me");</script>
              <p>Separate drafting from verification.</p>
            </article>
            <footer>Copyright</footer>
          </body>
        </html>
        """
        out = ah.extract_article_from_html(raw)
        self.assertEqual(out["title"], "Agent Harnesses")
        self.assertEqual(out["byline"], "Alex Builder")
        self.assertIn("Deterministic gates keep LLM workflows reliable.", out["text"])
        self.assertNotIn("ignore me", out["text"])
        self.assertNotIn("Home About", out["text"])
        self.assertGreaterEqual(out["word_count"], 10)

    def test_filter_candidates_enforces_topic_promo_and_dedup(self) -> None:
        cfg = ah.load_config(self.tmp)
        stories = [
            {"id": 1, "title": "LLM agent evaluation harnesses", "url": "https://a.test/1", "score": 200, "descendants": 80, "by": "u1"},
            {"id": 2, "title": "Browser is now in alpha", "url": "https://a.test/2", "score": 400, "descendants": 100, "by": "u2"},
            {"id": 3, "title": "AI startup raises $50M", "url": "https://a.test/3", "score": 300, "descendants": 50, "by": "u3"},
            {"id": 4, "title": "Claude coding workflow notes", "url": "https://a.test/4", "score": 250, "descendants": 40, "by": "u4"},
            {"id": 5, "title": "Small LLM post", "url": "https://a.test/5", "score": 10, "descendants": 2, "by": "u5"},
        ]
        result = ah.filter_candidates(stories, cfg, seen_ids={"4"})
        self.assertEqual([r["id"] for r in result], [1])
        self.assertEqual(result[0]["hn_url"], "https://news.ycombinator.com/item?id=1")

    def test_weighted_len_counts_placeholder_and_urls_as_23(self) -> None:
        self.assertEqual(ah.weighted_len("Read: {ARTICLE_URL}", url_weight=23), 6 + 23)
        long_url = "https://example.com/" + ("a" * 80)
        self.assertEqual(ah.weighted_len(f"Link {long_url}", url_weight=23), 5 + 23)

    def test_all_gates_pass_on_valid_run(self) -> None:
        self._write_valid_run()
        self.assertEqual(ah.gate_select(self.day, self.tmp), [])
        self.assertEqual(ah.gate_source(self.day, self.tmp), [])
        self.assertEqual(ah.gate_understand(self.day, self.tmp), [])
        self.assertEqual(ah.gate_posts(self.day, self.tmp), [])

    def test_gate_posts_catches_overlong_banned_and_missing_link(self) -> None:
        self._write_valid_run()
        bad_posts = {
            "title": "Bad thread",
            "source_url": "https://example.com/bad",
            "thread": [
                {"text": "This game-changer is wild! " + ("x" * 270), "images": []},
                {"text": "Second post without link.", "images": []},
                {"text": "Third post without link.", "images": []},
            ],
            "followups": [
                {"text": "Thoughts?", "images": []},
            ],
        }
        (self.rd / "posts.json").write_text(json.dumps(bad_posts), encoding="utf-8")
        errs = ah.gate_posts(self.day, self.tmp)
        joined = "\n".join(errs)
        self.assertIn("length", joined)
        self.assertIn("banned phrase", joined)
        self.assertIn("{ARTICLE_URL}", joined)

    def test_gate_understand_catches_missing_section(self) -> None:
        self._write_valid_run()
        (self.rd / "understanding.md").write_text("## Problem\nOnly one section.\n", encoding="utf-8")
        errs = ah.gate_understand(self.day, self.tmp)
        self.assertTrue(any("Central point" in e for e in errs))

    def test_render_and_record_outcome(self) -> None:
        self._write_valid_run()
        rendered = ah.render_posts(self.day, self.tmp)
        self.assertIn("https://example.com/agent-gates", rendered)
        self.assertNotIn("{ARTICLE_URL}", rendered)

        entry = ah.record_outcome(
            day=self.day,
            status="posted",
            thread_id="111",
            followup_id="222",
            x_handle="tester",
            root=self.tmp,
        )
        self.assertEqual(entry["id"], "999999")
        self.assertEqual(entry["x_ids"]["thread1"], "111")
        # Duplicate selection gate should now fail
        self.assertTrue(ah.gate_select(self.day, self.tmp))
        progress = (self.tmp / "PROGRESS.md").read_text(encoding="utf-8")
        self.assertIn("recorded posted", progress)


if __name__ == "__main__":
    unittest.main()
