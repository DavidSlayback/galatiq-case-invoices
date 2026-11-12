# 08 — Idempotent payment and rejection log

**Source:** [08-payment.md](../../tickets/08-payment.md)
**Type:** AFK
**Blocked by:** 03 (needs the payment.pay seam)
**Wave:** 3
**Lane:** payment
**Verifier profile:** self-check
**What it delivers:** `payment.pay` calls the brief's `mock_payment(vendor, amount)` at most once per vendor+number+revision, retries injected failures twice and then sends to the inbox, and rejections log their reasons and bad lines.

## Context
- Why: FR-4; the never-pay-twice guarantee needed by D2.
- Constraining decisions: A7: keep the brief's signature and add an injectable failure hook. D4: a rejection lists the bad lines rather than short-paying.
- Failure paths: A double call in the same run or across runs → one `paid` event. A crash between payment and event → payments has a unique key, so a retry sees the existing row.
- Plan anchors: PRD FR-4; D4, A7

## Acceptance criteria
- [ ] UNIQUE(vendor, invoice_number, revision) on payments
- [ ] A second pay of the same key → no mock_payment call, a `payment_skipped_already_paid` event
- [ ] Forced failure → 2 attempts, `payment_failed`, an inbox row
- [ ] A rejection event payload has the reason, finding IDs and bad lines

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_payment.py` — idempotency plus failure tests pass

## Change surface
- invoice_agents/payment.py, tests/test_payment.py
- Conflict risk: low: owns payment.py

## Out of scope
- Real banking
- Partial payment

## Completion evidence
- Test output
