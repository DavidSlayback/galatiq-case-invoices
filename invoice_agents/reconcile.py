"""Arithmetic reconciliation of an extracted invoice (FR-1.8, D14).

Shared by the extraction self-correction loop and the ARITHMETIC_MISMATCH rule,
so both judge consistency the same way.
"""

from decimal import Decimal

from invoice_agents.models import Invoice

CENT = Decimal("0.01")


def _line_total(qty: Decimal, price: Decimal | None, amount: Decimal | None) -> Decimal | None:
    if amount is not None:
        return amount
    return None if price is None else qty * price


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
