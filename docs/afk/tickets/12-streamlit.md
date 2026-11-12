# 12 — Streamlit dashboard

**Source:** [12-streamlit.md](../../tickets/12-streamlit.md)
**Type:** AFK
**Blocked by:** 11 (the UI inbox reuses inbox.py)
**Wave:** 8
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** `main.py ui` launches Streamlit with Process, Inbox, History and Batch pages over the same DB and graph.

## Context
- Why: D18 and the brief's UI/UX criterion.
- Constraining decisions: D18: Streamlit was chosen over Textual and FastAPI+HTMX because it is pure Python and easy for graders to click. Offline is the default in the UI and live backends follow D32 auto-detect once ticket 17 lands. Screenshots are taken headless with the pre-installed Playwright/Chromium.
- Failure paths: An upload of an unsupported type → an inline error. A DB locked by the CLI → WAL handles it, with retry and a toast.
- Plan anchors: PRD FR-5.6; D18

## Acceptance criteria
- [ ] AppTest renders every page with no exception
- [ ] Process: pick 1012 → stages, findings with rule IDs, decision, the why
- [ ] Inbox: approve with a note → the status updates
- [ ] History: the event timeline and trace link
- [ ] Batch: run all → scorecard
- [ ] Screenshots of each page saved to docs/img/ at deviceScaleFactor 2

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_app_smoke.py` — pass

## Change surface
- app/streamlit_app.py, app/pages/*.py, invoice_agents/cli.py (ui cmd), tests/test_app_smoke.py, docs/img/
- Conflict risk: low

## Out of scope
- The ROI page (ticket 16)

## Completion evidence
- Screenshots
- AppTest output
