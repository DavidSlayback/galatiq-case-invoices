# 10 — Duplicate and revision ledger, batch mode, history command

**Source:** [10-ledger-batch.md](../../tickets/10-ledger-batch.md)
**Type:** AFK
**Blocked by:** 09 (the eval is the regression net for the ledger change)
**Wave:** 6
**Lane:** ledger
**Verifier profile:** self-check
**What it delivers:** The ledger skips same-content copies, supersedes revisions with a logged diff, escalates post-payment deltas, adds `--invoice_dir` batch mode and `main.py history INV-x`.

## Context
- Why: D2 and D25: never pay twice, and a referable history of replacements (David, 2026-11-12).
- Constraining decisions: Key = vendor + number + revision. Duplicate = same key and the same sha256 of the canonical Invoice JSON, not file bytes (the PDF and TXT copies differ). Same key with different content → DUPLICATE_NUMBER_CONFLICT (fraud). A higher revision: original unpaid → superseded, inbox row withdrawn, new one processed; original paid → superseded plus the delta escalated as `revision_after_payment` (A8).
- Failure paths: A revision lower than the existing one → STALE_REVISION (soft) and the original is kept. Vendor-name variance between copies → normalise before keying.
- Plan anchors: PRD FR-2.10, FR-5.5; D2, D25, A8

## Acceptance criteria
- [ ] The batch over data/invoices shows the 1011/1012/1013 second copies as duplicate_skipped
- [ ] Scenario test: original in the inbox, then R1 → superseded, inbox withdrawn, one payment
- [ ] Eval order: 1004 paid, then R1 → superseded with diff {+GadgetX×5, +$4,050}, inbox row, no second payment
- [ ] `history INV-1004` prints the timeline with actors and diffs
- [ ] The `pending: ticket 10` rows in expected_outcomes.yaml are now real and passing

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run python main.py eval --offline` — exit 0, no pending rows
- `uv run python main.py --invoice_dir data/invoices --offline` — summary table with 3 duplicate_skipped

## Change surface
- invoice_agents/ledger.py, invoice_agents/graph.py (ledger branch), invoice_agents/cli.py, eval/expected_outcomes.yaml, tests/test_ledger.py
- Conflict risk: medium: touches graph.py and expected_outcomes.yaml; serialise with 13 on the yaml only at merge

## Out of scope
- The inbox resolve flow (ticket 11)

## Completion evidence
- Batch output
- History output for 1004
