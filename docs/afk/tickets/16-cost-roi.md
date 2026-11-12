# 16 — Cost and latency telemetry and the ROI page

**Source:** [16-cost-roi.md](../../tickets/16-cost-roi.md)
**Type:** AFK
**Blocked by:** 12 (the ROI page lives in the Streamlit app)
**Wave:** 9
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** Per-stage tokens, $ and seconds in traces and on invoice rows; a Streamlit ROI page with editable, labelled assumptions.

## Context
- Why: D21, NFR-11; translates the system into the $2M / 5-day / 30% story.
- Constraining decisions: D21: editable assumptions; no invented volume. The price table lives in settings, read from the claude-api skill's pricing reference at implementation time, with its date. Offline runs show $0 measured and label the figures 'offline: no model cost'; real numbers arrive with ticket 19.
- Failure paths: A missing price for a model → cost shown as 'unknown', never 0.
- Plan anchors: PRD NFR-11; D21

## Acceptance criteria
- [ ] The batch summary shows per-invoice $ and seconds
- [ ] The ROI page recomputes when inputs change (AppTest)
- [ ] Every assumed number is labelled 'assumption'

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_telemetry.py tests/test_app_smoke.py` — pass

## Change surface
- invoice_agents/telemetry.py, invoice_agents/settings.py (prices), app/pages/roi.py, tests/test_telemetry.py
- Conflict risk: low

## Out of scope
- Live cost measurement (ticket 19)

## Completion evidence
- ROI page screenshot
