# 19 · Live model pass on Claude Haiku

- **Blocked by:** 09, 14, 15; David sorting out API credits and a spend cap
- **Source:** David 2026-11-12 (no live calls unattended); A2, A4
- **Status:** todo (HITL)

## What
Add `main.py eval --record` to run the live model (`anthropic:claude-haiku-5-5`) over every file, write recordings to `tests/fixtures/recorded/` and diff them against the hand-written goldens. Then run a live eval with measured cost, including a live vision pass on the scanned 1011.

## Acceptance
- [ ] A diff report of recordings against goldens, with each difference resolved and its reason recorded
- [ ] Live eval ≥ 16/17 originals; no adversarial fraud file paid
- [ ] Measured $ per invoice is fed to the ROI page; total spend reported

## Verify
```bash
uv run python main.py eval --record && uv run python main.py eval
```

## Docs
docs/scorecard.md, docs/STATUS.md

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
