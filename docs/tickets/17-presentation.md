# 17 · README, Artifact deck and demo video

- **Blocked by:** 12, 13, 14, 15, 16
- **Source:** D24
- **Status:** todo

## What
Rewrite the README: problem, quickstart, generated Mermaid graph, the decision log summary with trade-offs, rule table link, scorecard, ROI, limitations and roadmap (PO three-way match, stock reservation). Then a Claude Artifact presentation and a 2–3 minute demo video (record-demo-video skill).

## Surfaces
README.md, docs/*, artifact, demo video

## Acceptance
- [ ] A fresh clone and the README quickstart reproduce the scorecard
- [ ] The Artifact link and the video file are listed in STATUS

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README (the whole thing)

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
