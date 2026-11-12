"""Validation rules. Each rule is a pure function returning findings with stable IDs (A5)."""

import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from invoice_agents.models import Finding, Invoice


@dataclass(frozen=True)
class Catalog:
    """Reference data the rules read: stock and catalog price per SKU."""

    stock: dict[str, int]
    price: dict[str, Decimal]

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> Catalog:
        """Read the inventory table."""
        rows = conn.execute("SELECT item, stock, unit_price FROM inventory").fetchall()
        return cls({r["item"]: r["stock"] for r in rows}, {r["item"]: Decimal(r["unit_price"]) for r in rows})


@dataclass(frozen=True)
class Ctx:
    """Everything a rule may look at."""

    invoice: Invoice
    catalog: Catalog
    as_of: date


Rule = Callable[[Ctx], list[Finding]]


def qty_by_sku(inv: Invoice) -> dict[str, Decimal]:
    """Total quantity per known SKU across all lines (FR-2.6: 1013 splits SKUs over several lines)."""
    out: dict[str, Decimal] = defaultdict(Decimal)
    for ln in inv.lines:
        if ln.sku:
            out[ln.sku] += ln.quantity
    return dict(out)


def unknown_item(c: Ctx) -> list[Finding]:
    """Lines whose item is not in inventory."""
    return [
        Finding(
            rule_id="UNKNOWN_ITEM",
            severity="hard",
            message=f"'{ln.item_raw}' is not in inventory",
            evidence={"item": ln.item_raw},
        )
        for ln in c.invoice.lines
        if not ln.sku or ln.sku not in c.catalog.stock
    ]


def stock_exceeded(c: Ctx) -> list[Finding]:
    """Summed quantity per SKU above stock (D1: literal stock check)."""
    return [
        Finding(
            rule_id="STOCK_EXCEEDED",
            severity="hard",
            message=f"{sku}: invoiced {qty}, in stock {c.catalog.stock[sku]}",
            evidence={"sku": sku, "invoiced": str(qty), "stock": c.catalog.stock[sku]},
        )
        for sku, qty in sorted(qty_by_sku(c.invoice).items())
        if sku in c.catalog.stock and c.catalog.stock[sku] > 0 and qty > c.catalog.stock[sku]
    ]


RULES: list[Rule] = [unknown_item, stock_exceeded]


def validate(invoice: Invoice, conn: sqlite3.Connection, as_of: date) -> list[Finding]:
    """Run every registered rule against one invoice."""
    ctx = Ctx(invoice, Catalog.load(conn), as_of)
    return [f for rule in RULES for f in rule(ctx)]
