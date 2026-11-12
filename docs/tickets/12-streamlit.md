# 12 · Streamlit dashboard

- **Blocked by:** 11
- **Source:** D18, FR-5.6
- **Status:** todo

## What
Pages: Process (upload or pick a sample, watch each stage update, findings with rule IDs, the decision and why); Inbox (approve or reject with a note); History (event timeline per invoice, link to the JSONL trace); Batch (run all, scorecard). Uses the same `graph.process` and DB. `main.py ui` launches it.

## Surfaces
app/streamlit_app.py, app/pages/*.py, tests/test_app_smoke.py (streamlit.testing.AppTest)

## Acceptance
- [ ] AppTest renders every page without exceptions
- [ ] Screenshots of every page saved to docs/img/

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: UI screenshots

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
