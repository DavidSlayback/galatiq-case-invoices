# 09 · Eval harness and scorecard on the 17 originals

- **Blocked by:** 05, 06, 07, 08
- **Source:** D20
- **Status:** todo

## What
`eval/expected_outcomes.yaml` is PRD §5 adjusted for D2 and D10: the decision plus the rule IDs that must fire for each file. `main.py eval [--offline] [--record]` runs a fresh DB over `data/invoices/` in a fixed order and prints a Rich scorecard (pass/fail, missing or extra rule IDs, cost, latency). The exit code is non-zero on any failure. Offline eval runs inside pytest.

## Surfaces
eval/expected_outcomes.yaml, invoice_agents/eval.py, tests/test_eval_offline.py

## Acceptance
- [ ] `eval --offline` 17/17 and part of pytest
- [ ] Live `eval` ≥ 16/17 within $5; the scorecard is saved to docs/scorecard.md

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q && uv run python main.py eval --offline
```

## Docs
README: scorecard section
