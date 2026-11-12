# 02 — Domain types and SQLite store with the append-only event ledger

**Source:** [02-domain-and-db.md](../../tickets/02-domain-and-db.md)
**Type:** AFK
**Blocked by:** 01 (needs the package and gate)
**Wave:** 1
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** Typed domain models plus a seeded SQLite database whose `invoice_events` table cannot be updated or deleted, with event+status writes in one transaction.

## Context
- Why: Every stage records events (D25), and validation needs inventory, prices, vendors and FX rates (D5, D6, D9).
- Constraining decisions: D25: events plus a status table written in the same transaction; pure event sourcing was rejected because every query and the inbox would need a fold. D17: business data in SQLite, agent traces in JSONL. A5: a Finding has a rule_id and a severity of hard, soft, fraud or note. A6: EUR→USD 1.08 dated 2026-01-31, mock. D9: known vendors are Widgets Inc., Gadgets Co., Precision Parts Ltd., Acme Industrial Supplies, MegaWidgets Corp, Consolidated Materials Group, Summit Manufacturing Co., FastShip Ltd. (alias QuickShip Distributers), Atlas Industrial Supply, TechParts International, Reliable Components Inc.
- Failure paths: An UPDATE or DELETE on events must raise. A status update that fails must roll back its event. `reset` on an existing DB must be idempotent. Concurrent CLI and Streamlit access: use WAL mode.
- Plan anchors: PLAN §Seams (models, db); D2, D17, D25

## Acceptance criteria
- [ ] Models: RawDocument, LineItem, Invoice (vendor, invoice_number, revision, dates, currency, lines, subtotal, tax, shipping, total, terms, notes, field provenance), Finding, Decision, Outcome
- [ ] Tables: inventory(item, stock, unit_price), vendors(name, address, known, aliases_json, bank_ref), fx_rates, invoices (key vendor + invoice_number, with revision and content_hash columns, D2), invoice_events, findings, payments (vendor, invoice_number, revision, amount_paid, currency, usd_equivalent; UNIQUE(vendor, invoice_number, revision)), inbox
- [ ] `db.enqueue_inbox(key, reason, label)` helper used by 07, 08 and 10 (11 only reads and resolves)
- [ ] Event types are an Enum covering D25 as amended: received, extracted, duplicate_skipped, superseded, validated, decided, guardrail_override, escalated, withdrawn, human_decision, paid, payment_skipped_already_paid, payment_failed, revision_after_payment
- [ ] BEFORE UPDATE/DELETE triggers on invoice_events RAISE(ABORT)
- [ ] `db.record(event, status_update)` is atomic; a test injects a failure and sees no event row
- [ ] `main.py reset` seeds WidgetA 15/$250, WidgetB 10/$500, GadgetX 5/$750, FakeItem 0/$0, the D9 vendors and A6's rate

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run python main.py reset && sqlite3 inventory.db 'select * from inventory'` — 4 rows as seeded

## Change surface
- invoice_agents/{models,db,seed}.py, tests/test_db.py
- Conflict risk: medium: models.py and db.py are imported by every later ticket; freeze the field names here

## Out of scope
- Rules and agents
- Migrations tooling (the schema is created fresh on reset)

## Completion evidence
- Trigger test output
- Seeded row dump
