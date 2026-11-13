"""Ledger identity, duplicate detection, revisions and what has been paid (D2, D25, A8).

An invoice is keyed by vendor + invoice number; the revision is carried
alongside. Duplicates are judged on a *core fingerprint* of the extracted
content, not file bytes: the PDF and TXT copies of one invoice differ in bytes
and even in which optional fields they state (1011's PDF has no subtotal).
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import timedelta
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


# Statuses a run passes through on its way to an outcome. An invoice left in one of them
# (or escalated with its inbox item already answered) was cut off mid-run.
_IN_FLIGHT = ("received", "extracted", "validated", "escalated")


# A run that has not touched its invoice for this long is dead. Worst case for a live run:
# 3 extraction attempts plus 2 VP-and-critic rounds (4 calls), each capped at the CLI
# bridge's 180 s timeout, is 7 x 180 s = 21 min; every event also refreshes the row.
RUN_STALE_AFTER = timedelta(minutes=30)


def _interrupted(conn: sqlite3.Connection, key: InvoiceKey, row: sqlite3.Row) -> bool:
    """A run died after recording this invoice but before it reached an outcome (D46).

    True when the status row has not moved for ``RUN_STALE_AFTER``, no inbox item is open,
    and no payment was started for this revision (a pending payment is the payment sweep's
    job). Re-running the file then processes it again instead of skipping it as a duplicate.
    The threshold is derived from the agent timeouts, so a live run never qualifies.
    """
    if row["status"] not in _IN_FLIGHT or not db.is_stale(row["updated_at"], RUN_STALE_AFTER):
        return False
    if _last_event(conn, key) == "human_decision":  # a person decided: never re-judge (sweep_unsettled_decisions)
        return False
    open_item = conn.execute(
        "SELECT 1 FROM inbox WHERE vendor=? AND invoice_number=? AND status='open'", (key.vendor, key.invoice_number)
    ).fetchone()
    return open_item is None and db.payment_state(conn, key) is None


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
        if bad:
            return Conflict(bad)
        return New() if _interrupted(conn, key, row) else Duplicate(row["status"], row["source_path"])
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
        amount_due: What is still owed when anything was already paid on this invoice (an earlier
            revision, a conflict copy, or this revision before a crash, D46); else ``None``.
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
    # Anything already paid on this invoice (an earlier revision, or this one before a crash
    # cut its run short) sends the rest to a person rather than an agent (A8, D46).
    paid = already_paid(conn, key.vendor, key.invoice_number)
    if paid > 0 and inv.total is not None:
        amount_due = inv.total - paid
    db.record(conn, key, EventType.EXTRACTED, actor="extractor", run_id=run_id, payload=extracted,
              status=Status.EXTRACTED)  # fmt: skip
    return Intake(key, verdict, findings=findings, amount_due=amount_due)


# Events a skipped re-run writes: they record that a copy arrived, not a step of the invoice's
# own run, so they must never hide the step a crash cut short.
_ARRIVALS = "('received', 'duplicate_skipped')"


def _last_event(conn: sqlite3.Connection, key: InvoiceKey) -> str | None:
    """The invoice's latest event, ignoring arrivals of copies."""
    row = conn.execute(
        "SELECT event FROM invoice_events WHERE vendor=? AND invoice_number=?"
        f" AND event NOT IN {_ARRIVALS} ORDER BY id DESC LIMIT 1",
        (key.vendor, key.invoice_number),
    ).fetchone()
    return None if row is None else row[0]


UNSETTLED = "decision_unsettled"


def sweep_unsettled_decisions(conn: sqlite3.Connection, run_id: str) -> int:
    """Put back in the inbox any human decision a dead process recorded but never carried out (D46).

    A decision is written (and its inbox item closed) before settlement runs, so a crash in
    between leaves the invoice escalated with nothing open. Re-judging it would risk paying
    what a person rejected, so the run-recovery path skips it and this sweep asks the person
    again, quoting the earlier decision. A pending payment is the payment sweep's job instead.

    Returns:
        How many invoices were queued.
    """
    rows = conn.execute(
        "SELECT i.vendor, i.invoice_number, i.revision, e.payload FROM invoices i"
        " JOIN invoice_events e ON e.id = (SELECT max(id) FROM invoice_events"
        f"   WHERE vendor=i.vendor AND invoice_number=i.invoice_number AND event NOT IN {_ARRIVALS})"
        " WHERE i.status='escalated' AND e.event='human_decision' AND i.updated_at<=?"
        " AND NOT EXISTS (SELECT 1 FROM inbox WHERE vendor=i.vendor AND invoice_number=i.invoice_number"
        "   AND status='open')"
        " AND NOT EXISTS (SELECT 1 FROM payments WHERE vendor=i.vendor AND invoice_number=i.invoice_number"
        "   AND revision=i.revision AND status='pending')",
        (db.cutoff(db.STALE_AFTER),),
    ).fetchall()
    for r in rows:
        earlier = json.loads(r[3])
        db.enqueue_inbox(
            conn, InvoiceKey(r[0], r[1], r[2]), reason=UNSETTLED, run_id=run_id, actor="ledger",
            payload={"earlier_decision": earlier.get("kind"), "earlier_note": earlier.get("note"),
                     "note": "a recorded decision was never carried out; decide again"},
        )  # fmt: skip
    return len(rows)
