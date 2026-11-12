"""Ledger identity, duplicate detection, revisions and what has been paid (D2, D25, A8).

An invoice is keyed by vendor + invoice number; the revision is carried
alongside. Duplicates are judged on a *core fingerprint* of the extracted
content, not file bytes: the PDF and TXT copies of one invoice differ in bytes
and even in which optional fields they state (1011's PDF has no subtotal).
"""

import json
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from invoice_agents.models import Finding, Invoice, InvoiceKey

CORE_FIELDS = ("vendor", "invoice_number", "revision", "invoice_date", "due_date", "total", "lines")


def key_for(inv: Invoice, file_sha256: str) -> InvoiceKey:
    """Ledger key for an extracted invoice; placeholders keep unidentifiable invoices distinct."""
    # NFKC + collapsed spaces here, case-insensitive columns in the DB: "WIDGETS  INC." is Widgets Inc. (B1).
    vendor = " ".join(unicodedata.normalize("NFKC", inv.vendor or "").split()) or "(missing vendor)"
    number = (inv.invoice_number or "").strip() or f"(no number {file_sha256[:8]})"
    return InvoiceKey(vendor, number, inv.revision)


def core(inv: Invoice) -> dict[str, Any]:
    """The fields that identify an invoice's content, as JSON-safe values (None = not stated)."""
    lines = [[ln.sku or ln.item_raw, str(ln.quantity), str(ln.unit_price)] for ln in inv.lines]
    return {
        "vendor": inv.vendor,
        "invoice_number": inv.invoice_number,
        "revision": inv.revision,
        "invoice_date": inv.invoice_date and inv.invoice_date.isoformat(),
        "due_date": inv.due_date and inv.due_date.isoformat(),
        "total": None if inv.total is None else str(inv.total),
        "lines": lines or None,
    }


def conflicts(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Core fields stated in both and different; a field missing on one side is compatible."""
    return [k for k in CORE_FIELDS if a.get(k) is not None and b.get(k) is not None and a[k] != b[k]]


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """What changed between two revisions: lines added and removed, and the total delta."""
    o = [tuple(x) for x in old.get("lines") or []]
    n = [tuple(x) for x in new.get("lines") or []]
    delta = Decimal(new["total"] or 0) - Decimal(old["total"] or 0)
    return {
        "lines_added": [list(x) for x in n if x not in o],
        "lines_removed": [list(x) for x in o if x not in n],
        "total_before": old["total"],
        "total_after": new["total"],
        "total_delta": str(delta),
    }


@dataclass(frozen=True)
class New:
    """Not seen before."""


@dataclass(frozen=True)
class Duplicate:
    """Same invoice, same revision, compatible content: skip."""

    original_status: str
    original_path: str | None


@dataclass(frozen=True)
class Conflict:
    """Same number and revision but different content: a fraud signal."""

    fields: list[str]


@dataclass(frozen=True)
class Revision:
    """A higher revision of a known invoice."""

    previous_revision: int
    changes: dict[str, Any]
    already_paid: Decimal
    open_inbox_ids: list[int] = field(default_factory=list[int])


@dataclass(frozen=True)
class Stale:
    """A lower revision than the one on file."""

    current_revision: int


Check = New | Duplicate | Conflict | Revision | Stale


def check(conn: sqlite3.Connection, key: InvoiceKey, inv: Invoice) -> Check:
    """Compare an extracted invoice with what the ledger already holds for its vendor and number."""
    row = conn.execute(
        "SELECT * FROM invoices WHERE vendor=? AND invoice_number=?", (key.vendor, key.invoice_number)
    ).fetchone()
    if row is None or row["core"] is None:
        return New()
    old, new = json.loads(row["core"]), core(inv)
    if inv.revision == row["revision"]:
        bad = conflicts(old, new)
        return Conflict(bad) if bad else Duplicate(row["status"], row["source_path"])
    if inv.revision < row["revision"]:
        return Stale(row["revision"])
    inbox = conn.execute(
        "SELECT id FROM inbox WHERE vendor=? AND invoice_number=? AND status='open'", (key.vendor, key.invoice_number)
    ).fetchall()
    return Revision(
        previous_revision=row["revision"],
        changes=diff(old, new),
        already_paid=already_paid(conn, key.vendor, key.invoice_number),
        open_inbox_ids=[r[0] for r in inbox],
    )


def split_findings(conn: sqlite3.Connection, key: InvoiceKey, inv: Invoice, limit: Decimal) -> list[Finding]:
    """Same vendor, same invoice date, each under the limit but together over it: a split to dodge review."""
    if inv.total is None or inv.invoice_date is None or inv.total >= limit:
        return []
    rows = conn.execute(
        "SELECT invoice_number, core FROM invoices WHERE vendor=? AND invoice_number<>? AND core IS NOT NULL",
        (key.vendor, key.invoice_number),
    ).fetchall()
    day = inv.invoice_date.isoformat()
    siblings = [
        (r["invoice_number"], Decimal(c["total"]))
        for r in rows
        if (c := json.loads(r["core"]))["invoice_date"] == day
        and c["total"] is not None
        and Decimal(c["total"]) < limit
    ]
    combined = inv.total + sum((t for _, t in siblings), Decimal(0))
    if not siblings or combined < limit:
        return []
    msg = f"{len(siblings) + 1} invoices from {key.vendor} dated {day} total {combined}, each under {limit}"
    return [
        Finding(
            rule_id="SPLIT_INVOICE_SUSPECTED", severity="fraud", message=msg,
            evidence={"with": [n for n, _ in siblings], "combined": str(combined)},
        )
    ]  # fmt: skip


CONFLICT_SUFFIX = " (conflict "


def base_number(invoice_number: str) -> str:
    """The invoice number without the suffix a conflicting copy gets."""
    return invoice_number.split(CONFLICT_SUFFIX)[0]


def already_paid(conn: sqlite3.Connection, vendor: str, invoice_number: str) -> Decimal:
    """Total paid so far across every revision and copy of one invoice (B7: conflicts count too)."""
    rows = conn.execute(
        "SELECT amount_paid FROM payments WHERE vendor=? AND (invoice_number=? OR invoice_number LIKE ?)",
        (vendor, base_number(invoice_number), base_number(invoice_number) + CONFLICT_SUFFIX + "%"),
    ).fetchall()
    return sum((Decimal(r[0]) for r in rows), Decimal(0))
