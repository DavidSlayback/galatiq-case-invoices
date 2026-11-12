"""SQLite store: inventory, vendors, ledger, append-only event log and inbox.

Every state change goes through :func:`record`, which appends an event and
updates the invoice's status row in one transaction (D25). Triggers make the
event table append-only.
"""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoice_agents.models import EventType, InvoiceKey, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    item TEXT PRIMARY KEY, stock INTEGER NOT NULL, unit_price TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vendors (
    name TEXT PRIMARY KEY, address TEXT, known INTEGER NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]', bank_ref TEXT);
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT PRIMARY KEY, usd_rate TEXT NOT NULL, as_of TEXT NOT NULL, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices (
    vendor TEXT NOT NULL, invoice_number TEXT NOT NULL, revision INTEGER NOT NULL,
    status TEXT NOT NULL, content_hash TEXT, total TEXT, currency TEXT, source_path TEXT,
    updated_at TEXT NOT NULL, PRIMARY KEY (vendor, invoice_number));
CREATE TABLE IF NOT EXISTS invoice_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, run_id TEXT NOT NULL,
    vendor TEXT NOT NULL, invoice_number TEXT NOT NULL, revision INTEGER NOT NULL,
    event TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON invoice_events
    BEGIN SELECT RAISE(ABORT, 'invoice_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON invoice_events
    BEGIN SELECT RAISE(ABORT, 'invoice_events is append-only'); END;
CREATE TABLE IF NOT EXISTS findings (
    run_id TEXT NOT NULL, vendor TEXT NOT NULL, invoice_number TEXT NOT NULL, revision INTEGER NOT NULL,
    rule_id TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL, evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments (
    vendor TEXT NOT NULL, invoice_number TEXT NOT NULL, revision INTEGER NOT NULL,
    amount_paid TEXT NOT NULL, currency TEXT NOT NULL, usd_equivalent TEXT NOT NULL, ts TEXT NOT NULL,
    UNIQUE (vendor, invoice_number, revision));
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, vendor TEXT NOT NULL, invoice_number TEXT NOT NULL,
    revision INTEGER NOT NULL, reason TEXT NOT NULL, label TEXT, status TEXT NOT NULL DEFAULT 'open',
    created_ts TEXT NOT NULL, resolved_ts TEXT, note TEXT, amount_due TEXT);
"""


def now() -> str:
    """UTC timestamp in ISO 8601."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database in WAL mode (the CLI and Streamlit may share it) and ensure the schema."""
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
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
        (ts, run_id, key.vendor, key.invoice_number, key.revision, event, actor, _json(payload or {})),
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
        conn.execute(
            "INSERT INTO inbox (vendor, invoice_number, revision, reason, label, created_ts, amount_due)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key.vendor, key.invoice_number, key.revision, reason, label, now(), _opt(amount_due)),
        )
        _record(
            conn,
            key,
            EventType.ESCALATED,
            actor,
            run_id,
            {"reason": reason, "label": label, **(payload or {})},
            Status.ESCALATED,
            {},
        )


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
