"""Human review of escalated invoices (D19, A3).

A decision needs a note, writes a ``human_decision`` event, and then runs the
same payment or rejection code the graph uses. Nothing pauses a graph run, so
resolving is a short follow-on step from the stored state.
"""

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from invoice_agents import db, fx, identity, payment
from invoice_agents.models import EventType, InvoiceKey, Status
from invoice_agents.trace import new_run_id


class InboxError(ValueError):
    """The request cannot be carried out (unknown item, already resolved, missing note, not approvable)."""


@dataclass(frozen=True)
class Item:
    """One open inbox entry with what a reviewer needs to decide."""

    id: int
    key: InvoiceKey
    reason: str
    label: str | None
    total: str | None
    currency: str | None
    amount_due: str | None
    risk: int | None
    flags: list[str]
    reasoning: list[str]
    created: str


def _latest_findings(conn: sqlite3.Connection, key: InvoiceKey) -> list[sqlite3.Row]:
    run = conn.execute(
        "SELECT run_id FROM findings WHERE vendor=? AND invoice_number=? ORDER BY rowid DESC LIMIT 1",
        (key.vendor, key.invoice_number),
    ).fetchone()
    if run is None:
        return []
    return conn.execute(
        "SELECT * FROM findings WHERE run_id=? AND vendor=? AND invoice_number=?",
        (run[0], key.vendor, key.invoice_number),
    ).fetchall()


def _reasoning(conn: sqlite3.Connection, key: InvoiceKey) -> list[str]:
    """Reasons from the most recent decision, plus the critic's last objections if the review deadlocked."""
    row = conn.execute(
        "SELECT payload FROM invoice_events WHERE vendor=? AND invoice_number=? AND event='decided' ORDER BY id DESC",
        (key.vendor, key.invoice_number),
    ).fetchone()
    # The first reason is the escalation code (already shown as "why"); the rest is the substance.
    return list(json.loads(row[0]).get("reasons", []))[1:] if row else []


def list_open(conn: sqlite3.Connection) -> list[Item]:
    """Open inbox items, oldest first."""
    out: list[Item] = []
    for r in conn.execute("SELECT * FROM inbox WHERE status='open' ORDER BY id").fetchall():
        key = InvoiceKey(r["vendor"], r["invoice_number"], r["revision"])
        inv = db.invoice_row(conn, key.vendor, key.invoice_number)
        findings = _latest_findings(conn, key)
        risk = next((json.loads(f["evidence"]).get("score") for f in findings if f["rule_id"] == "VENDOR_RISK"), None)
        out.append(
            Item(
                id=r["id"], key=key, reason=r["reason"], label=r["label"],
                total=inv["total"] if inv else None, currency=inv["currency"] if inv else None,
                amount_due=r["amount_due"], risk=risk,
                flags=sorted({f["rule_id"] for f in findings if f["severity"] != "note"}),
                reasoning=_reasoning(conn, key), created=r["created_ts"],
            )
        )  # fmt: skip
    return out


def _find(conn: sqlite3.Connection, invoice_number: str, vendor: str | None, inbox_id: int | None) -> sqlite3.Row:
    if inbox_id is not None:
        rows = conn.execute("SELECT * FROM inbox WHERE id=?", (inbox_id,)).fetchall()
    else:
        sql, args = "SELECT * FROM inbox WHERE invoice_number=?", [identity.lookup_number(invoice_number)]
        if vendor:
            sql, args = sql + " AND vendor=?", [*args, vendor]
        rows = conn.execute(sql + " ORDER BY id DESC", args).fetchall()
    if not rows:
        raise InboxError(f"{invoice_number} is not in the inbox")
    open_rows = [r for r in rows if r["status"] == "open"]
    if not open_rows:
        raise InboxError(f"{invoice_number} is not open (status: {rows[0]['status']}; {rows[0]['note'] or ''})")
    if len({identity.fold(r["vendor"]) for r in open_rows}) > 1:  # B3: never guess which vendor's invoice to pay
        names = ", ".join(sorted({r["vendor"] for r in open_rows}))
        raise InboxError(f"{invoice_number} is open for several vendors ({names}); name the vendor")
    return open_rows[0]


def resolve(
    conn: sqlite3.Connection,
    invoice_number: str,
    *,
    approve: bool,
    note: str,
    reviewer: str,
    vendor: str | None = None,
    inbox_id: int | None = None,
) -> dict[str, Any]:
    """Approve (and pay) or reject one escalated invoice.

    Args:
        conn: Open connection.
        invoice_number: Ledger invoice number, e.g. ``INV-1012``.
        approve: True to approve and pay, False to reject.
        note: Required justification, stored on the event.
        reviewer: Who decided, e.g. ``human:cli``.
        vendor: Disambiguates when two vendors use the same invoice number.
        inbox_id: The exact inbox item (the dashboard passes this).

    Returns:
        What happened: status, and the amount paid if any.

    Raises:
        InboxError: Missing note, unknown or closed item, or an invoice that cannot be approved.
    """
    if not note.strip():
        raise InboxError("a note is required for every human decision")
    r = _find(conn, invoice_number, vendor, inbox_id)
    key = InvoiceKey(r["vendor"], r["invoice_number"], r["revision"])
    inv = db.invoice_row(conn, key.vendor, key.invoice_number)
    hard = [f["rule_id"] for f in _latest_findings(conn, key) if f["severity"] == "hard"]
    if approve and hard:  # D15: approval with a hard finding is impossible, for humans too
        raise InboxError(f"cannot approve: hard findings {', '.join(hard)}")
    if approve and (inv is None or inv["total"] is None):
        raise InboxError("cannot approve: nothing usable was extracted; reject it or reprocess the file")
    run_id = new_run_id()
    decision = {"kind": "approve" if approve else "reject", "note": note, "inbox_id": r["id"], "reason": r["reason"]}
    db.record(conn, key, EventType.HUMAN_DECISION, actor=reviewer, run_id=run_id, payload=decision)
    with conn:
        conn.execute("UPDATE inbox SET status='resolved', resolved_ts=?, note=? WHERE id=?", (db.now(), note, r["id"]))
    if not approve:
        db.record(
            conn, key, EventType.REJECTED, actor=reviewer, run_id=run_id,
            payload={"reasons": [note]}, status=Status.REJECTED,
        )  # fmt: skip
        return {"status": Status.REJECTED.value}
    assert inv is not None
    total = Decimal(inv["total"])
    usd = fx.to_usd(total, inv["currency"] or "USD", fx.rates(conn))
    res = payment.pay(conn, key, total, inv["currency"] or "USD", usd, run_id)
    return {"status": res.status.value, "amount": str(res.amount)}
