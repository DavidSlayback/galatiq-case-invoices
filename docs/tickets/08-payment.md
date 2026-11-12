# 08 · Idempotent payment and rejection log

- **Blocked by:** 03
- **Source:** FR-4.*, A7
- **Status:** todo

## What
`mock_payment` keeps the brief's signature. A payment is keyed by vendor+number+revision; a second call is a no-op. Injectable failure → 2 attempts → `payment_failed` → inbox. Rejections write the reason, the findings and the bad lines (D4).

## Surfaces
invoice_agents/payment.py, tests/test_payment.py

## Acceptance
- [ ] Paying the same key twice gives one `paid` event
- [ ] Forced failure: 2 attempts, then the inbox

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
none

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
