"""Read-only lookups the review agents can call as tools (D48).

The VP and the critic see a case brief, but some judgement calls need context the
brief leaves out: has Acme paid this vendor before, and what does the catalog say
about an item? These functions answer from the ledger and the reference tables.
They never write, so a prompt-injected agent gains nothing by calling them.
"""

import re
import sqlite3
from decimal import Decimal
from typing import Any

from invoice_agents.models import InvoiceKey

RECENT = 5  # invoices listed in a vendor history; enough to show a pattern, small enough to read
# Earlier invoices' numbers are whatever their senders wrote (normalize keeps any string with a
# digit), so anything that is not a plain identifier is withheld from the reviewers (D52).
PLAIN_NUMBER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/#-]{0,31}")
WITHHELD = "(unusual invoice number withheld)"


def _number(n: str) -> str:
    """An earlier invoice's number as the reviewers see it: plain identifiers only."""
    return n if PLAIN_NUMBER.fullmatch(n) else WITHHELD


def vendor_history(conn: sqlite3.Connection, key: InvoiceKey) -> dict[str, Any]:
    """Acme's record with this invoice's vendor, excluding the invoice under review.

    Returns:
        ``in_registry`` (the payee is a registered vendor; the ledger key already resolves
        exact names and aliases, so this is the identity check), ``invoices_on_file`` (count by
        status), ``total_paid`` (sum of sent payments, by currency), ``recent`` (the latest
        invoices: number, status, total, currency) and ``open_review_items`` (inbox items still
        waiting on a person). A registered vendor with no history is normal for its first
        invoice; the ``note`` says so, because a live critic once read an empty history as an
        unconfirmed payee.
    """
    others = "vendor=? AND invoice_number<>?"
    args = (key.vendor, key.invoice_number)
    by_status = dict(
        conn.execute(f"SELECT status, count(*) FROM invoices WHERE {others} GROUP BY status", args).fetchall()
    )
    paid: dict[str, Decimal] = {}
    for currency, amount in conn.execute(
        f"SELECT currency, amount_paid FROM payments WHERE {others} AND status='sent'", args
    ).fetchall():
        paid[currency] = paid.get(currency, Decimal(0)) + Decimal(amount)
    recent = conn.execute(
        f"SELECT invoice_number, status, total, currency FROM invoices WHERE {others} ORDER BY updated_at DESC LIMIT ?",
        (*args, RECENT),
    ).fetchall()
    open_items = conn.execute(f"SELECT count(*) FROM inbox WHERE {others} AND status='open'", args).fetchone()[0]
    registered = conn.execute("SELECT 1 FROM vendors WHERE name=?", (key.vendor,)).fetchone() is not None
    first = not by_status
    return {
        "vendor": key.vendor,
        "in_registry": registered,
        "note": (
            ("Registered vendor" if registered else "NOT in the vendor registry")
            + ("; no earlier invoices on file (normal for a first invoice)" if first else "")
        ),
        "invoices_on_file": by_status,
        "total_paid": {c: str(a) for c, a in paid.items()},
        "recent": [{**dict(r), "invoice_number": _number(r["invoice_number"])} for r in recent],
        "open_review_items": open_items,
    }


def catalog_item(conn: sqlite3.Connection, sku: str) -> dict[str, Any]:
    """Catalog price and stock for one SKU, or ``{"sku": ..., "in_catalog": False}``."""
    row = conn.execute("SELECT item, stock, unit_price FROM inventory WHERE item=?", (sku,)).fetchone()
    if row is None:
        return {"sku": sku, "in_catalog": False}
    return {"sku": row["item"], "in_catalog": True, "stock": row["stock"], "unit_price": row["unit_price"]}
