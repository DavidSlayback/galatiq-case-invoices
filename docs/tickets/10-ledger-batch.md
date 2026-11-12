# 10 · Duplicate and revision ledger, batch mode, history

- **Blocked by:** 09
- **Source:** D2, D25, FR-5.5
- **Status:** todo

## What
Key: vendor + invoice number + revision. Duplicate test: a hash of the canonical extracted `Invoice` JSON, not the file bytes, because the PDF and TXT copies of 1011–1013 differ byte-wise. Same key and same content hash → `duplicate_skipped`, whatever the first copy's status. Same key with different content → `DUPLICATE_NUMBER_CONFLICT`, a fraud finding. A higher revision with the original unpaid → `superseded` (old/new revision, line and amount diff, reason) and the new one is processed. A higher revision with the original paid → the delta is escalated to the inbox. `--invoice_dir` batch mode prints a summary table. `main.py history INV-x` renders the event timeline.

## Surfaces
invoice_agents/ledger.py, invoice_agents/cli.py, tests/test_ledger.py

## Acceptance
- [ ] The batch shows 1011/1012/1013 second copies skipped
- [ ] Original unpaid (held in the inbox) then R1 arrives: a `superseded` event, the original is withdrawn from the inbox, R1 is processed, one payment
- [ ] Eval order (1004 auto-paid first, then R1): a `superseded` event with a +$4,050 diff, and only the delta goes to the inbox as `revision_after_payment`; it is never paid automatically
- [ ] The eval batch still passes

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q && uv run python main.py eval --offline
```

## Docs
README: ledger and history
