"""Payment stage: the brief's mock banking API behind an idempotent ledger write (FR-4, D2, D29, D41).

A payment is an outbox: the pending row is written before the bank is called
and settled after it answers. If the process dies in between, the pending row
stays, and the next attempt sends the invoice to a person to check the bank
(``payment_unconfirmed``) instead of paying again.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from invoice_agents import db, ledger
from invoice_agents.models import EventType, InvoiceKey, Status

ATTEMPTS = 2  # A7
UNCONFIRMED = "payment_unconfirmed"

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
    """Pay what is still owed on an approved invoice, at most once per revision.

    The amount is the invoice total minus anything already paid (or pending) on
    earlier revisions, so a revision after payment pays only the difference (D2).

    Args:
        conn: Open connection.
        key: Invoice and revision being paid.
        total: Approved invoice total in the invoice currency.
        currency: Invoice currency; payment goes out in it (D29).
        usd_equivalent: Total in USD, recorded alongside.
        run_id: Current run.
        bank: Payment API; injectable so tests can simulate failures.

    Returns:
        PAID with the amount sent; PAID with zero if this revision was already paid;
        PAYMENT_FAILED after the retry budget; ESCALATED if an earlier attempt's outcome is
        unknown. The last two leave the invoice in the inbox.
    """
    state = db.payment_state(conn, key)
    if state and state[0] == "sent":
        db.record(conn, key, EventType.PAYMENT_SKIPPED_ALREADY_PAID, actor="payment", run_id=run_id)
        return PaymentResult(Status.PAID, Decimal(0))
    if state:  # pending: an earlier attempt died after (or before) calling the bank, so never guess
        amount = state[1]
        if not db.has_open_inbox(conn, key, UNCONFIRMED):
            db.enqueue_inbox(conn, key, reason=UNCONFIRMED, run_id=run_id, actor="payment", amount_due=amount,
                             payload={"note": "check the bank before confirming or cancelling"})  # fmt: skip
        return PaymentResult(Status.ESCALATED, amount)
    amount = total - ledger.already_paid(conn, key.vendor, key.invoice_number)
    if amount <= 0:  # B6: a revision below what was paid is a credit to recover, never a bank payment
        db.record(conn, key, EventType.PAYMENT_SKIPPED_ALREADY_PAID, actor="payment", run_id=run_id,
                  payload={"credit_due": str(-amount)})  # fmt: skip
        return PaymentResult(Status.PAID, Decimal(0))
    # Scale the USD figure to the amount actually sent (a revision delta pays only part of the total).
    usd = (amount * usd_equivalent / total).quantize(Decimal("0.01")) if usd_equivalent and total else amount
    db.start_payment(conn, key, amount, currency, usd)
    errors: list[str] = []
    for _ in range(ATTEMPTS):
        try:
            if bank(key.vendor, amount).get("status") == "success":
                break
            errors.append("bank returned non-success")
        except Exception as e:  # the bank is an external boundary; any failure is retried, then escalated
            errors.append(f"{type(e).__name__}: {e}")
    else:
        db.fail_payment(conn, key, run_id=run_id, actor="payment", amount=amount,
                        payload={"amount": amount, "currency": currency, "errors": errors})  # fmt: skip
        return PaymentResult(Status.PAYMENT_FAILED, amount)
    db.settle_payment(conn, key, run_id=run_id, actor="payment",
                      payload={"amount": amount, "currency": currency, "usd_equivalent": usd})  # fmt: skip
    return PaymentResult(Status.PAID, amount)


def confirm_pending(conn: sqlite3.Connection, key: InvoiceKey, run_id: str, actor: str) -> PaymentResult:
    """A person saw the unconfirmed payment at the bank: settle it without sending again."""
    state = db.payment_state(conn, key)
    if state is None or state[0] != "pending":
        raise ValueError(f"no unconfirmed payment for {key}")
    amount = state[1]
    db.settle_payment(conn, key, run_id=run_id, actor=actor, payload={"amount": amount, "confirmed_at_bank": True})
    return PaymentResult(Status.PAID, amount)


def cancel_pending(conn: sqlite3.Connection, key: InvoiceKey, run_id: str, actor: str) -> PaymentResult:
    """A person found no such payment at the bank: clear it; approving the new inbox item retries it."""
    state = db.payment_state(conn, key)
    if state is None or state[0] != "pending":
        raise ValueError(f"no unconfirmed payment for {key}")
    amount = state[1]
    db.fail_payment(conn, key, run_id=run_id, actor=actor, amount=amount,
                    payload={"amount": amount, "errors": ["not found at the bank"]})  # fmt: skip
    return PaymentResult(Status.PAYMENT_FAILED, amount)
