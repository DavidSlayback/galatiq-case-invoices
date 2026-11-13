"""Read-only lookups the review agents can call as tools (D48).

The VP and the critic see a case brief, but some judgement calls need context the
brief leaves out: has Acme paid this vendor before, and what does the catalog say
about an item? These functions answer from the ledger and the reference tables.
They never write, so a prompt-injected agent gains nothing by calling them.
"""

import sqlite3
from decimal import Decimal
from typing import Any

from invoice_agents.models import InvoiceKey

RECENT = 5  # invoices listed in a vendor history; enough to show a pattern, small enough to read


def vendor_history(conn: sqlite3.Connection, key: InvoiceKey) -> dict[str, Any]:
    """Acme's record with this invoice's vendor, excluding the invoice under review.

    Returns:
        ``invoices_on_file`` (count by status), ``total_paid`` (sum of sent payments, by
        currency), ``recent`` (the latest invoices: number, status, total, currency) and
        ``open_review_items`` (inbox items still waiting on a person). A vendor never seen
        before returns zero counts, which is itself a signal.
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
    return {
        "vendor": key.vendor,
        "invoices_on_file": by_status,
        "total_paid": {c: str(a) for c, a in paid.items()},
        "recent": [dict(r) for r in recent],
        "open_review_items": open_items,
    }


def catalog_item(conn: sqlite3.Connection, sku: str) -> dict[str, Any]:
    """Catalog price and stock for one SKU, or ``{"sku": ..., "in_catalog": False}``."""
    row = conn.execute("SELECT item, stock, unit_price FROM inventory WHERE item=?", (sku,)).fetchone()
    if row is None:
        return {"sku": sku, "in_catalog": False}
    return {"sku": row["item"], "in_catalog": True, "stock": row["stock"], "unit_price": row["unit_price"]}
