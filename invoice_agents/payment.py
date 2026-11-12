"""Payment stage: the brief's mock banking API plus the ledger write."""

import sqlite3
from decimal import Decimal

from invoice_agents import db
from invoice_agents.models import EventType, InvoiceKey, Status


def mock_payment(vendor: str, amount: Decimal | float) -> dict[str, str]:
    """The brief's mock payment API."""
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}


def pay(conn: sqlite3.Connection, key: InvoiceKey, amount: Decimal, currency: str, run_id: str) -> Decimal:
    """Pay an approved invoice and record it.

    Returns:
        The amount paid.
    """
    mock_payment(key.vendor, amount)
    with conn:
        conn.execute(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key.vendor, key.invoice_number, key.revision, str(amount), currency, str(amount), db.now()),
        )
    db.record(
        conn,
        key,
        EventType.PAID,
        actor="payment",
        run_id=run_id,
        payload={"amount": str(amount), "currency": currency},
        status=Status.PAID,
    )
    return amount
