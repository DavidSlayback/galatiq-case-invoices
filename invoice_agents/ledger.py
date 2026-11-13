"""Ledger identity, duplicate detection, revisions and what has been paid (D2, D25, A8).

An invoice is keyed by vendor + invoice number; the revision is carried
alongside. Duplicates are judged on a *core fingerprint* of the extracted
content, not file bytes: the PDF and TXT copies of one invoice differ in bytes
and even in which optional fields they state (1011's PDF has no subtotal).
"""

import json
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from invoice_agents import db, identity
from invoice_agents.models import EventType, Finding, Invoice, InvoiceKey, Status

CORE_FIELDS = ("vendor", "invoice_number", "revision", "invoice_date", "due_date", "total", "lines")


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
    """Core fields stated in both and different; a field missing on one side is compatible.

    Vendor names compare without case or spacing (D36) but with NFKC differences kept,
    so a full-width or alias spelling is a conflict while "WIDGETS  INC." is a duplicate.
    """

    def differ(k: str) -> bool:
        x, y = a[k], b[k]
        return identity.plain(x) != identity.plain(y) if k == "vendor" else x != y

    return [k for k in CORE_FIELDS if a.get(k) is not None and b.get(k) is not None and differ(k)]


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
    """A higher revision of a known invoice; ``open_inbox_ids`` are the items it withdraws (never payment items)."""

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
    """Compare an extracted invoice with what the ledger already holds for its vendor and number.

    Read-only. Only the revision on file is compared: the same revision is a
    duplicate or a conflict, a lower one is stale, a higher one is a revision.
    """
    row = db.invoice_row(conn, key.vendor, key.invoice_number)
    if row is None or row["core"] is None:
        return New()
    old, new = json.loads(row["core"]), core(inv)
    if inv.revision == row["revision"]:
        bad = conflicts(old, new)
        return Conflict(bad) if bad else Duplicate(row["status"], row["source_path"])
    if inv.revision < row["revision"]:
        return Stale(row["revision"])
    inbox = conn.execute(
        # Payment items stay open: a revision must not hide money that may already have left.
        "SELECT id FROM inbox WHERE vendor=? AND invoice_number=? AND status='open'"
        " AND reason NOT IN ('payment_unconfirmed', 'payment_failed', 'overpayment')",
        (key.vendor, key.invoice_number),
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


def already_paid(conn: sqlite3.Connection, vendor: str, invoice_number: str) -> Decimal:
    """Total paid or possibly paid (pending), plus overpayments, across every revision and copy (B7)."""
    rows = conn.execute(
        "SELECT invoice_number, amount_paid FROM payments WHERE vendor=? AND status<>'cancelled'"
        " UNION ALL SELECT invoice_number, amount FROM overpayments WHERE vendor=?",
        (vendor, vendor),
    ).fetchall()
    return sum((Decimal(r[1]) for r in rows if identity.same_invoice(r[0], invoice_number)), Decimal(0))


@dataclass(frozen=True)
class Intake:
    """What receiving an invoice into the ledger decided.

    Attributes:
        key: The key to process under (a conflicting copy gets its own).
        verdict: Name of the ledger check result, for the trace.
        skipped: Why the invoice is not processed further (duplicate or stale), else ``None``.
        findings: Findings the ledger raises (STALE_REVISION, DUPLICATE_NUMBER_CONFLICT).
        amount_due: For a revision of a paid invoice, what is still owed; else ``None``.
    """

    key: InvoiceKey
    verdict: str
    skipped: dict[str, object] | None = None
    findings: list[Finding] = field(default_factory=list[Finding])
    amount_due: Decimal | None = None


def intake(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    inv: Invoice,
    *,
    source: dict[str, str],
    run_id: str,
    extracted: dict[str, object],
) -> Intake:
    """Check an extracted invoice against the ledger and record its receipt (D2, D25).

    Duplicates and stale revisions get RECEIVED and DUPLICATE_SKIPPED events and leave the
    status row of the copy on file alone. Everything else is recorded RECEIVED then EXTRACTED;
    a conflicting copy gets its own key, and a revision supersedes the original and withdraws
    its open inbox items. Each event is its own transaction.

    Args:
        conn: Open connection.
        key: Key from :func:`identity.key_for`.
        inv: The reconciled invoice.
        source: ``path``, ``sha256`` and ``format`` of the file.
        run_id: Current run.
        extracted: Payload for the EXTRACTED event (model, attempts, mismatches).
    """
    found = check(conn, key, inv)
    verdict = type(found).__name__
    findings: list[Finding] = []
    if isinstance(found, Duplicate | Stale):
        db.record(conn, key, EventType.RECEIVED, actor="intake", run_id=run_id, payload=dict(source))
        why: dict[str, object] = (
            {"duplicate_of": found.original_path, "original_status": found.original_status}
            if isinstance(found, Duplicate)
            else {"stale_revision": inv.revision, "current_revision": found.current_revision}
        )
        db.record(conn, key, EventType.DUPLICATE_SKIPPED, actor="ledger", run_id=run_id, payload=why)
        if isinstance(found, Stale):
            msg = f"revision {inv.revision} is older than revision {found.current_revision} on file"
            findings.append(Finding(rule_id="STALE_REVISION", severity="soft", message=msg))
        return Intake(key, verdict, skipped=why, findings=findings)
    if isinstance(found, Conflict):
        key = identity.conflict_key(key, source["sha256"])
        msg = f"same invoice number and revision as one on file, but {', '.join(found.fields)} differ"
        findings.append(Finding(rule_id="DUPLICATE_NUMBER_CONFLICT", severity="fraud", message=msg,
                                evidence={"fields": found.fields}))  # fmt: skip
    db.record(
        conn, key, EventType.RECEIVED, actor="intake", run_id=run_id, payload=dict(source),
        status=Status.RECEIVED, source_path=source["path"], total=inv.total, currency=inv.currency,
        core=json.dumps(core(inv)),
    )  # fmt: skip
    amount_due = None
    if isinstance(found, Revision):
        db.withdraw_inbox(conn, key, found.open_inbox_ids, run_id)
        db.record(
            conn, key, EventType.SUPERSEDED, actor="ledger", run_id=run_id,
            payload={"previous_revision": found.previous_revision, "revision": inv.revision,
                     "already_paid": str(found.already_paid), **found.changes},
        )  # fmt: skip
        if found.already_paid > 0 and inv.total is not None:
            amount_due = inv.total - found.already_paid
    db.record(conn, key, EventType.EXTRACTED, actor="extractor", run_id=run_id, payload=extracted,
              status=Status.EXTRACTED)  # fmt: skip
    return Intake(key, verdict, findings=findings, amount_due=amount_due)
