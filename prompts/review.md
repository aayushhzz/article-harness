# Stage: Review

Audit `runs/<day>/posts.json` against `runs/<day>/source.json` and `runs/<day>/understanding.md`.

## Checklist
1. Accuracy: every concrete claim matches `source.json`.
2. Hook: post 1 earns attention with a concrete situation, not vague hype.
3. Clarity: no jargon without context, no repeated sentences across posts.
4. Engagement: follow-up reply asks a sharp, concrete question builders actually disagree on.
5. Pass `python3 -m harness.article_harness gate posts --day <day>`.
