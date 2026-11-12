# 14 — Adversarial invoices and their eval rows

**Source:** [14-adversarial.md](../../tickets/14-adversarial.md)
**Type:** AFK
**Blocked by:** 13 (lookalike and risk rules must exist)
**Wave:** 7
**Lane:** adversarial
**Verifier profile:** full (untrusted parser)
**What it delivers:** New files in data/invoices/adversarial/ with eval rows: prompt injection, a same-day split under $10K, a lookalike vendor, a bank-detail change and a clean control.

## Context
- Why: D20, NFR-8; shows robustness beyond the brief.
- Constraining decisions: D10: none auto-reject on fraud alone; they go to the inbox. Split detection: two invoices from one vendor on the same date summing to ≥ $10K → SPLIT_INVOICE_SUSPECTED (fraud), added to rules. Bank change: an invoice states remit-to bank details different from the registry bank_ref → BANK_DETAILS_CHANGED (fraud). Offline goldens are hand-written as in 05.
- Failure paths: Injection text must not alter extraction fields or the decision; a test asserts the decision equals the control-equivalent outcome plus fraud flags.
- Plan anchors: PRD NFR-8; D10, D20

## Acceptance criteria
- [ ] No adversarial file reaches `paid` except the control
- [ ] The injection file's extracted fields match its golden (instructions ignored)
- [ ] `eval --offline` passes on originals plus adversarial files

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run python main.py eval --offline` — exit 0, adversarial rows included

## Change surface
- data/invoices/adversarial/*, invoice_agents/rules.py, eval/expected_outcomes.yaml, tests/fixtures/golden/
- Conflict risk: medium: rules.py and the yaml; runs after 13 in the same lane

## Out of scope
- Scanned adversarial PDFs (ticket 15 adds the scan)

## Completion evidence
- Scorecard incl. the adversarial section
