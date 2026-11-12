# 02 · Domain types and SQLite store with the event ledger

- **Blocked by:** 01
- **Source:** D17, D25, A5, A6
- **Status:** todo

## What
Pydantic models: `RawDocument`, `LineItem`, `Invoice` (with revision), `Finding(rule_id, severity, message, evidence)`, `Decision`. SQLite schema: `inventory(item, stock, unit_price)`; `vendors(name, address, known, aliases_json)`; `fx_rates`; `invoices` (current status per vendor+number+revision); `invoice_events` (append-only, with BEFORE UPDATE/DELETE triggers that RAISE); `findings`; `payments`; `inbox`. `db.record(event, status_update)` writes both in one transaction. `main.py reset` seeds the brief's 4 items with prices of $250/$500/$750/$0, the D9 vendors and the A6 rate.

## Surfaces
invoice_agents/{models,db}.py, invoice_agents/seed.py, tests/test_db.py

## Acceptance
- [ ] UPDATE and DELETE on `invoice_events` raise
- [ ] A failed status update rolls back its event (same transaction)
- [ ] `reset` produces the seeded rows the tests expect

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: data model section
