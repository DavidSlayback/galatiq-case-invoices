# 16 · Cost and latency tracking with the ROI panel

- **Blocked by:** 12
- **Source:** D21, NFR-11
- **Status:** todo

## What
Collect tokens, $ (a price table in settings) and seconds per stage and per invoice into the JSONL trace and the `invoices` row. A Streamlit ROI page takes editable assumptions (invoices per year, 30% error rate, 5-day delay, $2M per year), labels any assumed numbers, and computes projections from measured cost, latency and catch rate.

## Surfaces
invoice_agents/telemetry.py, app/pages/roi.py, tests/test_telemetry.py

## Acceptance
- [ ] The batch prints per-invoice $ and seconds
- [ ] The ROI page updates when the inputs change (AppTest)

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: business impact

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
