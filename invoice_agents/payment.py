"""Payment stage: the brief's mock banking API behind an idempotent ledger write (FR-4, D2, D29)."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from invoice_agents import db, ledger
from invoice_agents.models import EventType, InvoiceKey, Status

ATTEMPTS = 2  # A7

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

    The amount is the invoice total minus anything already paid on earlier
    revisions, so a revision after payment pays only the difference (D2).

    Args:
        conn: Open connection.
        key: Invoice and revision being paid.
        total: Approved invoice total in the invoice currency.
        currency: Invoice currency; payment goes out in it (D29).
        usd_equivalent: Total in USD, recorded alongside.
        run_id: Current run.
        bank: Payment API; injectable so tests can simulate failures.

    Returns:
        PAID with the amount sent, PAID with zero if this revision was already paid,
        or PAYMENT_FAILED after the retry budget (the invoice then sits in the inbox).
    """
    if conn.execute("SELECT 1 FROM payments WHERE vendor=? AND invoice_number=? AND revision=?", tuple(key)).fetchone():
        db.record(conn, key, EventType.PAYMENT_SKIPPED_ALREADY_PAID, actor="payment", run_id=run_id)
        return PaymentResult(Status.PAID, Decimal(0))
    amount = total - ledger.already_paid(conn, key.vendor, key.invoice_number)
    if amount <= 0:  # B6: a revision below what was paid is a credit to recover, never a bank payment
        db.record(conn, key, EventType.PAYMENT_SKIPPED_ALREADY_PAID, actor="payment", run_id=run_id,
                  payload={"credit_due": str(-amount)})  # fmt: skip
        return PaymentResult(Status.PAID, Decimal(0))
    errors: list[str] = []
    for _ in range(ATTEMPTS):
        try:
            if bank(key.vendor, amount).get("status") == "success":
                break
            errors.append("bank returned non-success")
        except Exception as e:  # the bank is an external boundary; any failure is retried, then escalated
            errors.append(f"{type(e).__name__}: {e}")
    else:
        db.record(
            conn, key, EventType.PAYMENT_FAILED, actor="payment", run_id=run_id,
            payload={"amount": amount, "currency": currency, "errors": errors}, status=Status.PAYMENT_FAILED,
        )  # fmt: skip
        db.enqueue_inbox(
            conn, key, reason="payment_failed", run_id=run_id, actor="payment", amount_due=amount,
            payload={"errors": errors},
        )  # fmt: skip
        return PaymentResult(Status.PAYMENT_FAILED, amount)
    # Scale the USD figure to the amount actually sent (a revision delta pays only part of the total).
    usd = (amount * usd_equivalent / total).quantize(Decimal("0.01")) if usd_equivalent and total else amount
    with conn:
        conn.execute(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*key, str(amount), currency, str(usd), db.now()),
        )
    db.record(
        conn, key, EventType.PAID, actor="payment", run_id=run_id,
        payload={"amount": amount, "currency": currency, "usd_equivalent": usd}, status=Status.PAID,
    )  # fmt: skip
    return PaymentResult(Status.PAID, amount)
