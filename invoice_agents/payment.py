"""Payment stage: the brief's mock banking API behind an idempotent ledger write (FR-4, D2, D29, D41).

A payment is an outbox: the pending row is written before the bank is called
and settled after it answers. A pending row is never re-sent, because the money
may already have left: if the process dies or the bank call raises, the next
:func:`pay` for that revision or :func:`sweep_unconfirmed` sends the invoice to a
person to check the bank (``payment_unconfirmed``) instead (D45).
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from invoice_agents import db, fx, ledger
from invoice_agents.models import EventType, InvoiceKey, Status

ATTEMPTS = 2  # A7
UNCONFIRMED = db.UNCONFIRMED_REASON
STALE_AFTER = db.STALE_AFTER

Bank = Callable[[str, Decimal], dict[str, str]]


def mock_payment(vendor: str, amount: Decimal | float) -> dict[str, str]:
    """The brief's mock payment API."""
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}


@dataclass(frozen=True)
class PaymentResult:
    """What happened when asked to pay."""

    status: Status
    amount: Decimal


def pay(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    total: Decimal,
    currency: str,
    usd_equivalent: Decimal | None,
    run_id: str,
    bank: Bank = mock_payment,
) -> PaymentResult:
    """Pay what is still owed on an approved invoice revision, never re-sending a call whose outcome is unknown.

    The amount is the invoice total minus anything already paid (or pending) on
    earlier revisions and conflict copies, so a revision after payment pays only
    the difference (D2). Only a definite refusal from the bank is retried, up to
    ``ATTEMPTS`` calls. Each ledger write is its own transaction (see :mod:`db`).

    Args:
        conn: Open connection.
        key: Invoice and revision being paid.
        total: Approved invoice total in the invoice currency.
        currency: Invoice currency; payment goes out in it (D29).
        usd_equivalent: Total in USD, recorded alongside.
        run_id: Current run.
        bank: Payment API; injectable so tests can simulate failures.

    Returns:
        PAID with the amount sent; PAID with zero if this revision was already paid or
        nothing is owed (a credit is recorded instead); PAYMENT_FAILED after the retry
        budget; ESCALATED if this or an earlier call's outcome is unknown, or another
        process holds the payment. PAYMENT_FAILED and unknown outcomes leave an inbox item.
    """
    state = db.payment_state(conn, key)
    if state and state[0] == "sent":
        db.record(conn, key, EventType.PAYMENT_SKIPPED_ALREADY_PAID, actor="payment", run_id=run_id)
        return PaymentResult(Status.PAID, Decimal(0))
    if state and state[0] == "pending":  # an earlier attempt died after (or before) the bank call: never guess
        _unconfirmed(conn, key, state[1], run_id, "an earlier attempt did not finish")
        return PaymentResult(Status.ESCALATED, state[1])
    amount = total - ledger.already_paid(conn, key.vendor, key.invoice_number)
    if amount <= 0:  # B6: a revision below what was paid is a credit to recover, never a bank payment
        db.record(conn, key, EventType.PAYMENT_SKIPPED_ALREADY_PAID, actor="payment", run_id=run_id,
                  payload={"credit_due": str(-amount)})  # fmt: skip
        return PaymentResult(Status.PAID, Decimal(0))
    # Scale the USD figure to the amount actually sent (a revision delta pays only part of the total).
    usd = (amount * usd_equivalent / total).quantize(fx.CENT) if usd_equivalent and total else amount
    attempt = db.start_payment(conn, key, amount, currency, usd)
    if attempt is None:  # another process claimed this payment between our check and now: never call the bank
        return PaymentResult(Status.ESCALATED, amount)
    errors: list[str] = []
    for _ in range(ATTEMPTS):
        try:
            reply = bank(key.vendor, amount)
        except Exception as e:  # a timeout or dropped connection may hide a payment that went out: never retry
            _unconfirmed(conn, key, amount, run_id, f"{type(e).__name__}: {e}")
            return PaymentResult(Status.ESCALATED, amount)
        if reply.get("status") == "success":
            break
        errors.append("bank returned non-success")  # a definite refusal: nothing was sent, so retrying is safe
    else:
        db.fail_payment(conn, key, attempt, run_id=run_id, actor="payment", amount=amount,
                        payload={"amount": amount, "currency": currency, "errors": errors})  # fmt: skip
        return PaymentResult(Status.PAYMENT_FAILED, amount)
    db.settle_payment(conn, key, attempt, run_id=run_id, actor="payment",
                      payload={"amount": amount, "currency": currency, "usd_equivalent": usd})  # fmt: skip
    return PaymentResult(Status.PAID, amount)


def confirm_pending(conn: sqlite3.Connection, key: InvoiceKey, run_id: str, actor: str) -> PaymentResult:
    """A person saw the unconfirmed payment at the bank: settle it without sending again.

    Raises:
        ValueError: No payment for this revision is pending.
    """
    amount, attempt = _pending(conn, key)
    db.settle_payment(conn, key, attempt, run_id=run_id, actor=actor,
                      payload={"amount": amount, "confirmed_at_bank": True})  # fmt: skip
    return PaymentResult(Status.PAID, amount)


def cancel_pending(conn: sqlite3.Connection, key: InvoiceKey, run_id: str, actor: str) -> PaymentResult:
    """A person found no such payment at the bank: cancel it; approving the new ``payment_failed`` item retries it.

    Raises:
        ValueError: No payment for this revision is pending.
    """
    amount, attempt = _pending(conn, key)
    db.fail_payment(conn, key, attempt, run_id=run_id, actor=actor, amount=amount,
                    payload={"amount": amount, "errors": ["not found at the bank"]})  # fmt: skip
    return PaymentResult(Status.PAYMENT_FAILED, amount)


def _pending(conn: sqlite3.Connection, key: InvoiceKey) -> tuple[Decimal, int]:
    found = db.pending_payment(conn, key)
    if found is None:
        raise ValueError(f"no unconfirmed payment for {key}")
    return found


def _unconfirmed(conn: sqlite3.Connection, key: InvoiceKey, amount: Decimal, run_id: str, why: str) -> None:
    """Queue a bank check for a pending payment, once: repeated sweeps and retries add no second item."""
    if not db.has_open_inbox(conn, key, UNCONFIRMED):
        db.enqueue_inbox(conn, key, reason=UNCONFIRMED, run_id=run_id, actor="payment", amount_due=amount,
                         payload={"error": why, "note": "check the bank before confirming or cancelling"})  # fmt: skip


def sweep_unconfirmed(conn: sqlite3.Connection, run_id: str, older_than: timedelta = STALE_AFTER) -> int:
    """Send every stale pending payment to a person; returns how many were found.

    A process that dies mid-payment leaves a pending row and nothing else, and re-running the
    file is a duplicate, so this sweep (run before processing and when the inbox is listed) is
    what surfaces it.
    """
    stale = db.stale_pending(conn, older_than)
    for key, amount in stale:
        _unconfirmed(conn, key, amount, run_id, "payment started but never finished")
    return len(stale)
