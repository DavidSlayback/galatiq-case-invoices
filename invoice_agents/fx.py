"""Currency conversion against the seeded mock rate table (D5, A6)."""

import sqlite3
from decimal import Decimal

CENT = Decimal("0.01")


def rates(conn: sqlite3.Connection) -> dict[str, Decimal]:
    """USD rate per currency code."""
    return {r["currency"]: Decimal(r["usd_rate"]) for r in conn.execute("SELECT * FROM fx_rates")}


def to_usd(amount: Decimal | None, currency: str, table: dict[str, Decimal]) -> Decimal | None:
    """Convert to USD, rounded to cents; None if the amount or the rate is unknown."""
    rate = table.get(currency.upper())
    if amount is None or rate is None:
        return None
    return (amount * rate).quantize(CENT)
