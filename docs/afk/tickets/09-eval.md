# 09 — Offline eval harness and scorecard on the 17 originals

**Source:** [09-eval.md](../../tickets/09-eval.md)
**Type:** AFK
**Blocked by:** 05 (goldens); 06 (rule IDs); 07 (routing); 08 (payment events)
**Wave:** 5
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** `main.py eval --offline` resets a temp DB, runs every original sample file in a fixed order, compares each against eval/expected_outcomes.yaml and prints a Rich scorecard; it runs inside pytest.

## Context
- Why: D20; the strongest proof of correctness; the regression net for every later ticket.
- Constraining decisions: Expected outcomes = PRD §5 adjusted by D2 (A8: in eval order 1004 is paid first, so R1 is superseded with its delta escalated — but the ledger arrives in ticket 10, so until then R1 is expected as a second independent invoice and this row is marked `pending: ticket 10`), D10 (fraud → inbox unless a hard rule rejects first), D4, D5 and D6. Each row asserts the decision, required rule IDs and forbidden rule IDs. A non-zero exit on any failure.
- Failure paths: A missing golden → that row fails with a clear reason, and the others still run. Duplicate copies until ticket 10 → rows marked `pending: ticket 10`, not failing.
- Plan anchors: PLAN §Acceptance evidence; D20, A8

## Acceptance criteria
- [ ] eval/expected_outcomes.yaml has one row per file (22 rows incl. the duplicate copies), each with a rationale comment
- [ ] `eval --offline` passes every non-pending row; pending rows are listed separately
- [ ] The scorecard shows file, expected, actual, missing/extra rule IDs, and seconds
- [ ] tests/test_eval_offline.py runs the eval
- [ ] The scorecard is written to docs/scorecard.md

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run python main.py eval --offline` — exit 0; all non-pending rows PASS

## Change surface
- eval/expected_outcomes.yaml, invoice_agents/eval.py, invoice_agents/cli.py, tests/test_eval_offline.py, docs/scorecard.md
- Conflict risk: medium: expected_outcomes.yaml is later edited by 10 and 14

## Out of scope
- Live eval (ticket 19)
- Adversarial files (ticket 14)

## Completion evidence
- Scorecard output
