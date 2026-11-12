# 06 — Validation rule registry

**Source:** [06-rules.md](../../tickets/06-rules.md)
**Type:** AFK
**Blocked by:** 03 (needs the rules.validate seam and Finding type)
**Wave:** 3
**Lane:** rules
**Verifier profile:** self-check
**What it delivers:** `rules.validate(invoice, db, as_of)` returns stable-ID findings for every FR-2 rule, and docs/RULES.md documents them.

## Context
- Why: FR-2.* plus the data-only traps: 1013 summed per SKU, 1005/1007 overruns, 1010 rush price, 1014 FX.
- Constraining decisions: D1: the stock check is literal (qty ≤ stock), with a README caveat rather than a PO match. D3: stock is never consumed. D5: convert with A6 before price rules. D6: only prices >5% over catalog are soft; discounts are notes. D8: dates are checked against as_of. D7: a total of $9.5K–$10K is NEAR_THRESHOLD (soft). D10: fraud-severity rules never reject by themselves.
- Failure paths: Lines with qty 0, missing price or unknown currency → findings, not exceptions. Unknown currency → UNSUPPORTED_CURRENCY (hard).
- Plan anchors: PRD FR-2; D1, D3, D5, D6, D7, D8, D10, A5

## Acceptance criteria
- [ ] Hard: UNKNOWN_ITEM, STOCK_EXCEEDED (summed per SKU), ZERO_STOCK_ITEM, NEGATIVE_QUANTITY, ARITHMETIC_MISMATCH, MISSING_VENDOR, MISSING_DUE_DATE, UNSUPPORTED_CURRENCY, LOAD_FAILED
- [ ] Soft: PRICE_OVER_CATALOG, NEAR_THRESHOLD, DUE_BEFORE_INVOICE, DUE_TERMS_MISMATCH, PAST_DUE, DATE_UNPARSEABLE
- [ ] Fraud: UNKNOWN_VENDOR, URGENCY_LANGUAGE, SUSPICIOUS_ADDRESS (seed list incl. 1600 Pennsylvania Ave)
- [ ] Notes: FOREIGN_CURRENCY, DISCOUNT_APPLIED
- [ ] 1013 golden → STOCK_EXCEEDED ×3; 1010 → PRICE_OVER_CATALOG on the rush line only; 1014 → notes only
- [ ] docs/RULES.md lists the ID, severity, rationale and the sample invoice that exercises each

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_rules.py` — one param per rule ID passes

## Change surface
- invoice_agents/{rules,fx}.py, tests/test_rules.py, docs/RULES.md
- Conflict risk: low: owns rules.py; vendor-registry rules (VENDOR_RENAMED, risk) are ticket 13

## Out of scope
- Vendor risk score and alias matching (ticket 13)
- Duplicate detection (ticket 10)

## Completion evidence
- Rule test output
- RULES.md
