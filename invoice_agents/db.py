"""SQLite store: inventory, vendors, ledger, append-only event log and inbox.

The store exposes business transitions, not tables: each function below is
one transaction that appends its event, updates the invoice's status row and
writes any payment, inbox or findings rows together (D25). Callers never issue
SQL against those tables. Triggers make the event table append-only.
"""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoice_agents import identity
from invoice_agents.models import EventType, Finding, InvoiceKey, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    item TEXT PRIMARY KEY, stock INTEGER NOT NULL, unit_price TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vendors (
    name TEXT PRIMARY KEY, address TEXT, known INTEGER NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]', bank_ref TEXT);
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT PRIMARY KEY, usd_rate TEXT NOT NULL, as_of TEXT NOT NULL, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices (
    vendor TEXT NOT NULL COLLATE FOLD, invoice_number TEXT NOT NULL COLLATE FOLD, revision INTEGER NOT NULL,
    status TEXT NOT NULL, content_hash TEXT, core TEXT, total TEXT, currency TEXT, source_path TEXT,
    updated_at TEXT NOT NULL, PRIMARY KEY (vendor, invoice_number));
CREATE TABLE IF NOT EXISTS invoice_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, run_id TEXT NOT NULL,
    vendor TEXT NOT NULL COLLATE FOLD, invoice_number TEXT NOT NULL COLLATE FOLD, revision INTEGER NOT NULL,
    event TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON invoice_events
    BEGIN SELECT RAISE(ABORT, 'invoice_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON invoice_events
    BEGIN SELECT RAISE(ABORT, 'invoice_events is append-only'); END;
CREATE TABLE IF NOT EXISTS findings (
    run_id TEXT NOT NULL, vendor TEXT NOT NULL COLLATE FOLD, invoice_number TEXT NOT NULL COLLATE FOLD,
    revision INTEGER NOT NULL,
    rule_id TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL, evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments (
    vendor TEXT NOT NULL COLLATE FOLD, invoice_number TEXT NOT NULL COLLATE FOLD, revision INTEGER NOT NULL,
    amount_paid TEXT NOT NULL, currency TEXT NOT NULL, usd_equivalent TEXT NOT NULL, ts TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    UNIQUE (vendor, invoice_number, revision));
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT NOT NULL COLLATE FOLD, invoice_number TEXT NOT NULL COLLATE FOLD,
    revision INTEGER NOT NULL, reason TEXT NOT NULL, label TEXT, status TEXT NOT NULL DEFAULT 'open',
    created_ts TEXT NOT NULL, resolved_ts TEXT, note TEXT, amount_due TEXT);
"""


def now() -> str:
    """UTC timestamp in ISO 8601."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def json_dumps(obj: Any) -> str:
    """Stable JSON for payload columns (Decimal and dates as strings)."""
    return json.dumps(obj, default=str, sort_keys=True)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database in WAL mode (the CLI and Streamlit may share it) and ensure the schema."""
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    identity.register(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(payments)")}
    if "status" not in cols:  # databases made before pending payments existed
        conn.execute("ALTER TABLE payments ADD COLUMN status TEXT NOT NULL DEFAULT 'sent'")
    return conn


def record(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    event: EventType,
    *,
    actor: str,
    run_id: str,
    payload: dict[str, Any] | None = None,
    status: Status | None = None,
    **invoice_fields: Any,
) -> None:
    """Append an event and, optionally, upsert the invoice status row atomically.

    Args:
        conn: Open connection.
        key: Invoice identity.
        event: Event type.
        actor: Who acted: a stage, rule, agent or ``human:<name>``.
        run_id: Run that produced the event.
        payload: Event details (JSON-serialisable).
        status: New status for the invoice row; ``None`` leaves it unchanged.
        **invoice_fields: Extra ``invoices`` columns to set (``content_hash``, ``total``,
            ``currency``, ``source_path``).

    Raises:
        sqlite3.Error: On any failure; nothing from this call is persisted.
    """
    with conn:
        _record(conn, key, event, actor, run_id, payload, status, invoice_fields)


def _record(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    event: EventType,
    actor: str,
    run_id: str,
    payload: dict[str, Any] | None,
    status: Status | None,
    invoice_fields: dict[str, Any],
) -> None:
    """Statements behind :func:`record`, without opening a transaction."""
    ts = now()
    conn.execute(
        "INSERT INTO invoice_events (ts, run_id, vendor, invoice_number, revision, event, actor, payload)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, run_id, key.vendor, key.invoice_number, key.revision, event, actor, json_dumps(payload or {})),
    )
    if status is not None:
        fields = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in invoice_fields.items()}
        cols = ["vendor", "invoice_number", "revision", "status", "updated_at", *fields]
        vals = [key.vendor, key.invoice_number, key.revision, status, ts, *fields.values()]
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols[2:])
        conn.execute(
            f"INSERT INTO invoices ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            f" ON CONFLICT (vendor, invoice_number) DO UPDATE SET {updates}",
            vals,
        )


def enqueue_inbox(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    *,
    reason: str,
    run_id: str,
    actor: str,
    label: str | None = None,
    amount_due: Decimal | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Put an invoice in the human-review inbox: event, status and inbox row in one transaction."""
    with conn:
        _enqueue(conn, key, reason, run_id, actor, label, amount_due, payload)


def _enqueue(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    reason: str,
    run_id: str,
    actor: str,
    label: str | None,
    amount_due: Decimal | None,
    payload: dict[str, Any] | None,
) -> None:
    """Statements behind :func:`enqueue_inbox`, without opening a transaction."""
    conn.execute(
        "INSERT INTO inbox (vendor, invoice_number, revision, reason, label, created_ts, amount_due)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key.vendor, key.invoice_number, key.revision, reason, label, now(), _opt(amount_due)),
    )
    payload = {"reason": reason, "label": label, **(payload or {})}
    _record(conn, key, EventType.ESCALATED, actor, run_id, payload, Status.ESCALATED, {})


def _opt(d: Decimal | None) -> str | None:
    return None if d is None else str(d)


def events(conn: sqlite3.Connection, vendor: str, invoice_number: str) -> list[sqlite3.Row]:
    """All events for one invoice, oldest first."""
    return conn.execute(
        "SELECT * FROM invoice_events WHERE vendor=? AND invoice_number=? ORDER BY id",
        (vendor, invoice_number),
    ).fetchall()


def invoice_row(conn: sqlite3.Connection, vendor: str, invoice_number: str) -> sqlite3.Row | None:
    """Current status row for one invoice, if any."""
    return conn.execute(
        "SELECT * FROM invoices WHERE vendor=? AND invoice_number=?", (vendor, invoice_number)
    ).fetchone()


def has_open_inbox(conn: sqlite3.Connection, key: InvoiceKey, reason: str) -> bool:
    """Whether this invoice revision already waits in the inbox for this reason."""
    return (
        conn.execute(
            "SELECT 1 FROM inbox WHERE vendor=? AND invoice_number=? AND revision=? AND reason=? AND status='open'",
            (*key, reason),
        ).fetchone()
        is not None
    )


def payment_state(conn: sqlite3.Connection, key: InvoiceKey) -> tuple[str, Decimal] | None:
    """``(pending|sent, amount)`` for one invoice revision, or ``None`` if nothing was attempted."""
    row = conn.execute(
        "SELECT status, amount_paid FROM payments WHERE vendor=? AND invoice_number=? AND revision=?", tuple(key)
    ).fetchone()
    return None if row is None else (row[0], Decimal(row[1]))


def start_payment(conn: sqlite3.Connection, key: InvoiceKey, amount: Decimal, currency: str, usd: Decimal) -> None:
    """Write the pending payment row before the bank is called, so a crash after the call leaves evidence."""
    with conn:
        conn.execute(
            "INSERT INTO payments (vendor, invoice_number, revision, amount_paid, currency, usd_equivalent, ts, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
            (*key, str(amount), currency, str(usd), now()),
        )


def settle_payment(
    conn: sqlite3.Connection, key: InvoiceKey, *, run_id: str, actor: str, payload: dict[str, Any]
) -> None:
    """Mark the pending payment sent and record PAID, in one transaction."""
    with conn:
        conn.execute(
            "UPDATE payments SET status='sent', ts=? WHERE vendor=? AND invoice_number=? AND revision=?",
            (now(), *key),
        )
        _record(conn, key, EventType.PAID, actor, run_id, payload, Status.PAID, {})


def fail_payment(
    conn: sqlite3.Connection, key: InvoiceKey, *, run_id: str, actor: str, amount: Decimal, payload: dict[str, Any]
) -> None:
    """Drop the pending row, record PAYMENT_FAILED and queue the invoice for a person, in one transaction."""
    with conn:
        conn.execute(
            "DELETE FROM payments WHERE vendor=? AND invoice_number=? AND revision=? AND status='pending'", tuple(key)
        )
        _record(conn, key, EventType.PAYMENT_FAILED, actor, run_id, payload, Status.PAYMENT_FAILED, {})
        _enqueue(conn, key, "payment_failed", run_id, actor, None, amount, {"errors": payload.get("errors", [])})


def record_findings(conn: sqlite3.Connection, key: InvoiceKey, run_id: str, findings: list[Finding]) -> None:
    """Store a run's findings and record VALIDATED, in one transaction."""
    with conn:
        conn.executemany(
            "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(run_id, *key, f.rule_id, f.severity, f.message, json_dumps(f.evidence)) for f in findings],
        )
        payload = {"findings": [f.model_dump() for f in findings]}
        _record(conn, key, EventType.VALIDATED, "rules", run_id, payload, Status.VALIDATED, {})


def withdraw_inbox(conn: sqlite3.Connection, key: InvoiceKey, inbox_ids: list[int], run_id: str) -> None:
    """Withdraw open inbox items a newer revision replaces, and record WITHDRAWN, in one transaction."""
    if not inbox_ids:
        return
    with conn:
        conn.executemany(
            "UPDATE inbox SET status='withdrawn', resolved_ts=?, note=? WHERE id=?",
            [(now(), f"superseded by revision {key.revision}", i) for i in inbox_ids],
        )
        payload = {"inbox_ids": inbox_ids, "reason": "superseded"}
        _record(conn, key, EventType.WITHDRAWN, "ledger", run_id, payload, None, {})


def resolve_inbox(
    conn: sqlite3.Connection, inbox_id: int, key: InvoiceKey, *, reviewer: str, run_id: str, decision: dict[str, Any]
) -> None:
    """Record a person's decision and close the inbox item, in one transaction."""
    with conn:
        _record(conn, key, EventType.HUMAN_DECISION, reviewer, run_id, decision, None, {})
        conn.execute(
            "UPDATE inbox SET status='resolved', resolved_ts=?, note=? WHERE id=?", (now(), decision["note"], inbox_id)
        )
