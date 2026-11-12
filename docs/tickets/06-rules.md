# 06 · Validation rule registry

- **Blocked by:** 03
- **Source:** FR-2.*, D1, D5, D6, D8, D9, A5
- **Status:** todo

## What
Every rule is a pure function returning `Finding`s with a stable ID and severity. Hard: UNKNOWN_ITEM, STOCK_EXCEEDED (quantities summed per SKU, FR-2.6), ZERO_STOCK_ITEM, NEGATIVE_QUANTITY, ARITHMETIC_MISMATCH, MISSING_VENDOR, MISSING_DUE_DATE. Soft: PRICE_OVER_CATALOG (>5% after FX), NEAR_THRESHOLD ($9.5K–$10K), DUE_BEFORE_INVOICE, DUE_TERMS_MISMATCH, PAST_DUE (against as_of), VENDOR_RENAMED. Fraud: UNKNOWN_VENDOR, URGENCY_LANGUAGE, SUSPICIOUS_ADDRESS. Notes: FOREIGN_CURRENCY, DISCOUNT_APPLIED. The rule table goes in the docs.

## Surfaces
invoice_agents/rules.py, invoice_agents/fx.py, tests/test_rules.py

## Acceptance
- [ ] One table-driven test per rule ID
- [ ] 1013 fires STOCK_EXCEEDED for all 3 SKUs while each single line passes
- [ ] 1014 converts at 1.08 with only FOREIGN_CURRENCY and DISCOUNT_APPLIED

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
docs/RULES.md (rule ID, severity, rationale)
