"""Arithmetic reconciliation of an extracted invoice (FR-1.8, D14).

Shared by the extraction self-correction loop and the ARITHMETIC_MISMATCH rule,
so both judge consistency the same way.
"""

import re
from datetime import timedelta
from decimal import Decimal

from invoice_agents.models import Finding, Invoice

CENT = Decimal("0.01")


def net_days(terms: str | None) -> int | None:
    """Days from 'Net N' terms, if stated."""
    m = re.search(r"net\s*(\d+)", terms or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


DATE_SLACK_DAYS = 45  # beyond any genuine terms variance in the samples (largest is -30, 1002)


def _line_total(qty: Decimal, price: Decimal | None, amount: Decimal | None) -> Decimal | None:
    if amount is not None:
        return amount
    return None if price is None else qty * price


def implausible_dates(inv: Invoice) -> list[str]:
    """Dates far off the stated terms: likely misread (a wrong year), worth one more look.

    Unlike arithmetic, these never become a finding by themselves; the date rules judge the final values.
    """
    days = net_days(inv.payment_terms)
    if days is None or not (inv.invoice_date and inv.due_date):
        return []
    expected = inv.invoice_date + timedelta(days=days)
    gap = (inv.due_date - expected).days
    if abs(gap) <= DATE_SLACK_DAYS:
        return []
    return [
        f"due date {inv.due_date} is {gap:+d} days from {inv.payment_terms} after {inv.invoice_date}; check the year"
    ]


def mismatches(inv: Invoice) -> list[str]:
    """Describe every stated figure that disagrees with the others.

    Checks qty x unit price against a stated line amount, the line sum against
    the subtotal, and subtotal + tax + shipping against the total (falling back
    to the line sum when no subtotal is stated).

    Returns:
        Human-readable mismatch descriptions with the numbers involved; empty if consistent.
    """
    out: list[str] = []
    totals: list[Decimal] = []
    for i, ln in enumerate(inv.lines, 1):
        if ln.unit_price is not None and ln.amount is not None:
            expected = ln.quantity * ln.unit_price
            if abs(expected - ln.amount) > CENT:
                out.append(
                    f"line {i} ({ln.item_raw}): {ln.quantity} x {ln.unit_price} = {expected}, stated {ln.amount}"
                )
        t = _line_total(ln.quantity, ln.unit_price, ln.amount)
        if t is not None:
            totals.append(t)
    line_sum = sum(totals, Decimal(0)) if len(totals) == len(inv.lines) and totals else None
    if line_sum is not None and inv.subtotal is not None and abs(line_sum - inv.subtotal) > CENT:
        out.append(f"lines sum to {line_sum}, stated subtotal {inv.subtotal}")
    base = inv.subtotal if inv.subtotal is not None else line_sum
    if base is not None and inv.total is not None:
        expected_total = base + (inv.tax or 0) + (inv.shipping or 0)
        if abs(expected_total - inv.total) > CENT:
            out.append(
                f"subtotal {base} + tax {inv.tax or 0} + shipping {inv.shipping or 0} = {expected_total},"
                f" stated total {inv.total}"
            )
    return out


def mismatch_finding(problems: list[str], attempts: int) -> Finding:
    """The hard finding for arithmetic that still does not add up after the retry budget (D14)."""
    return Finding(rule_id="ARITHMETIC_MISMATCH", severity="hard", message="; ".join(problems),
                   evidence={"attempts": attempts})  # fmt: skip
