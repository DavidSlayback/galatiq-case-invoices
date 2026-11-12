"""Validation rules. Each rule is a pure function returning findings with stable IDs (A5).

Severities: ``hard`` rejects, ``soft`` sends to VP review, ``fraud`` sends to a
human, ``note`` is informational (D7, D10). The rule table is documented in
docs/RULES.md.
"""

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from invoice_agents import fx
from invoice_agents.approval import AUTO_LIMIT
from invoice_agents.models import Finding, Invoice, Severity

NEAR_THRESHOLD_FROM = Decimal("9500")  # D27: 9,500 <= total < 10,000
PRICE_TOLERANCE = Decimal("0.05")  # D6: >5% over catalog
TERMS_TOLERANCE_DAYS = 1  # D26: vendors count terms inclusively

# Addresses that cannot be a supplier's (seed list; a real system would use an address-verification service).
SUSPICIOUS_ADDRESSES = ("1600 pennsylvania ave",)
URGENCY = re.compile(
    r"\b(urgent|immediately|immediate payment|wire transfer|avoid penalt\w*|final notice|act now)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class Reference:
    """Reference data the rules read."""

    stock: dict[str, int]
    price: dict[str, Decimal]
    vendors: dict[str, dict[str, object]]
    aliases: dict[str, str]
    rates: dict[str, Decimal]

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> Reference:
        """Read inventory, vendors and FX rates."""
        inv = conn.execute("SELECT item, stock, unit_price FROM inventory").fetchall()
        vend = conn.execute("SELECT * FROM vendors").fetchall()
        return cls(
            stock={r["item"]: r["stock"] for r in inv},
            price={r["item"]: Decimal(r["unit_price"]) for r in inv},
            vendors={norm(r["name"]): dict(r) for r in vend},
            aliases={norm(a): r["name"] for r in vend for a in json.loads(r["aliases_json"])},
            rates=fx.rates(conn),
        )


@dataclass(frozen=True)
class Ctx:
    """Everything a rule may look at."""

    invoice: Invoice
    ref: Reference
    as_of: date

    def usd(self, amount: Decimal | None) -> Decimal | None:
        """Amount converted to USD at the mock rate."""
        return fx.to_usd(amount, self.invoice.currency, self.ref.rates)


Rule = Callable[[Ctx], list[Finding]]


def norm(name: str | None) -> str:
    """Comparison form of a vendor name."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _f(rule_id: str, severity: Severity, message: str, **evidence: object) -> Finding:
    return Finding(rule_id=rule_id, severity=severity, message=message, evidence=evidence)


def qty_by_sku(inv: Invoice) -> dict[str, Decimal]:
    """Total quantity per SKU across all lines (FR-2.6: 1013 splits SKUs over several lines)."""
    out: dict[str, Decimal] = defaultdict(Decimal)
    for ln in inv.lines:
        if ln.sku:
            out[ln.sku] += ln.quantity
    return dict(out)


def vendor_known(c: Ctx) -> bool:
    """Exact registry match on the vendor name."""
    return norm(c.invoice.vendor) in c.ref.vendors


# --- hard -------------------------------------------------------------------


def unknown_item(c: Ctx) -> list[Finding]:
    """Lines whose item is not in inventory."""
    return [
        _f("UNKNOWN_ITEM", "hard", f"'{ln.item_raw}' is not in inventory", item=ln.item_raw)
        for ln in c.invoice.lines
        if not ln.sku or ln.sku not in c.ref.stock
    ]


def zero_stock_item(c: Ctx) -> list[Finding]:
    """Items carried at zero stock (FakeItem): nothing can be supplied against them."""
    return [
        _f("ZERO_STOCK_ITEM", "hard", f"{sku} has zero stock; invoiced {q}", sku=sku, invoiced=str(q))
        for sku, q in sorted(qty_by_sku(c.invoice).items())
        if c.ref.stock.get(sku) == 0 and q > 0
    ]


def stock_exceeded(c: Ctx) -> list[Finding]:
    """Summed quantity per SKU above stock (D1: literal stock check)."""
    return [
        _f(
            "STOCK_EXCEEDED",
            "hard",
            f"{sku}: invoiced {q}, in stock {c.ref.stock[sku]}",
            sku=sku,
            invoiced=str(q),
            stock=c.ref.stock[sku],
        )
        for sku, q in sorted(qty_by_sku(c.invoice).items())
        if c.ref.stock.get(sku, 0) > 0 and q > c.ref.stock[sku]
    ]


def non_positive_quantity(c: Ctx) -> list[Finding]:
    """Zero or negative quantities are data-integrity errors."""
    return [
        _f("NEGATIVE_QUANTITY", "hard", f"'{ln.item_raw}' has quantity {ln.quantity}", item=ln.item_raw)
        for ln in c.invoice.lines
        if ln.quantity <= 0
    ]


def missing_fields(c: Ctx) -> list[Finding]:
    """Fields an invoice cannot be paid without."""
    inv, out = c.invoice, []
    if not (inv.vendor or "").strip():
        out.append(_f("MISSING_VENDOR", "hard", "vendor name is missing"))
    if inv.due_date is None and not inv.due_date_raw:
        out.append(_f("MISSING_DUE_DATE", "hard", "due date is missing"))
    if inv.total is None:
        out.append(_f("MISSING_TOTAL", "hard", "total amount is missing"))
    if not inv.lines:
        out.append(_f("NO_LINE_ITEMS", "hard", "no line items"))
    return out


def unsupported_currency(c: Ctx) -> list[Finding]:
    """Currencies without a rate cannot be checked or paid."""
    cur = c.invoice.currency.upper()
    if cur in c.ref.rates:
        return []
    return [_f("UNSUPPORTED_CURRENCY", "hard", f"no exchange rate for {cur}", currency=cur)]


# --- soft -------------------------------------------------------------------


def price_vs_catalog(c: Ctx) -> list[Finding]:
    """Unit price in USD more than 5% above catalog is soft; below catalog is a note (D6)."""
    out: list[Finding] = []
    for ln in c.invoice.lines:
        cat = c.ref.price.get(ln.sku or "")
        usd = c.usd(ln.unit_price)
        if not cat or usd is None:
            continue
        if usd > cat * (1 + PRICE_TOLERANCE):
            pct = (usd / cat - 1) * 100
            msg = f"'{ln.item_raw}' at {usd} USD is {pct:.0f}% over catalog {cat}"
            out.append(_f("PRICE_OVER_CATALOG", "soft", msg, item=ln.item_raw, price=str(usd), catalog=str(cat)))
        elif usd < cat:
            msg = f"'{ln.item_raw}' at {usd} USD is below catalog {cat}"
            out.append(_f("DISCOUNT_APPLIED", "note", msg, item=ln.item_raw, price=str(usd), catalog=str(cat)))
    return out


def near_threshold(c: Ctx) -> list[Finding]:
    """Totals just under the auto-approval limit are a classic split or gaming signal (D27)."""
    t = c.usd(c.invoice.total)
    if t is not None and NEAR_THRESHOLD_FROM <= t < AUTO_LIMIT:
        return [_f("NEAR_THRESHOLD", "soft", f"total {t} USD is just under the {AUTO_LIMIT} limit", total=str(t))]
    return []


def net_days(terms: str | None) -> int | None:
    """Days from 'Net N' terms, if stated."""
    m = re.search(r"net\s*(\d+)", terms or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def due_dates(c: Ctx) -> list[Finding]:
    """Due-date checks: unparseable, before the invoice date, off the terms, past due (D26, D27)."""
    inv, out = c.invoice, []
    if inv.due_date is None:
        if inv.due_date_raw:
            msg = f"due date '{inv.due_date_raw}' is not a date"
            out.append(_f("DATE_UNPARSEABLE", "soft", msg, raw=inv.due_date_raw))
        return out
    if inv.invoice_date and inv.due_date <= inv.invoice_date:
        msg = f"due {inv.due_date} is not after the invoice date {inv.invoice_date}"
        out.append(_f("DUE_BEFORE_INVOICE", "soft", msg))
    days = net_days(inv.payment_terms)
    if inv.invoice_date and days is not None:
        expected = inv.invoice_date + timedelta(days=days)
        gap = (inv.due_date - expected).days
        if abs(gap) > TERMS_TOLERANCE_DAYS:
            msg = f"due {inv.due_date} vs {inv.payment_terms} from {inv.invoice_date} ({expected}): {gap:+d} days"
            out.append(_f("DUE_TERMS_MISMATCH", "soft", msg, gap_days=gap))
    if inv.due_date < c.as_of:
        out.append(_f("PAST_DUE", "soft", f"due {inv.due_date} is before {c.as_of}"))
    return out


def urgency_text(inv: Invoice) -> str:
    """Free-text fields where pressure language appears."""
    return " ".join(x for x in (inv.notes, inv.payment_terms, inv.due_date_raw) if x)


def vendor_checks(c: Ctx) -> list[Finding]:
    """Unknown vendor (soft), urgency (soft), both together (fraud), implausible address (fraud). D10, D27."""
    inv, out = c.invoice, []
    known = vendor_known(c) or not (inv.vendor or "").strip()  # a blank vendor is MISSING_VENDOR's job
    urgent = URGENCY.findall(urgency_text(inv))
    if not known:
        out.append(_f("UNKNOWN_VENDOR", "soft", f"'{inv.vendor}' is not in the vendor registry", vendor=inv.vendor))
    if urgent:
        out.append(_f("URGENCY_LANGUAGE", "soft", f"pressure language: {', '.join(urgent)}", phrases=urgent))
    if not known and urgent:
        msg = "unknown vendor demanding urgent payment"
        out.append(_f("UNKNOWN_VENDOR_PRESSURE", "fraud", msg, vendor=inv.vendor, phrases=urgent))
    addr = norm(inv.vendor_address)
    if any(s in addr for s in SUSPICIOUS_ADDRESSES):
        out.append(_f("SUSPICIOUS_ADDRESS", "fraud", f"implausible vendor address: {inv.vendor_address}"))
    return out


# --- notes ------------------------------------------------------------------


def foreign_currency(c: Ctx) -> list[Finding]:
    """Non-USD invoices are converted at the mock rate (D5)."""
    cur = c.invoice.currency.upper()
    if cur == "USD" or cur not in c.ref.rates:
        return []
    t = c.usd(c.invoice.total)
    return [_f("FOREIGN_CURRENCY", "note", f"{c.invoice.total} {cur} = {t} USD at {c.ref.rates[cur]}")]


RULES: list[Rule] = [
    unknown_item,
    zero_stock_item,
    stock_exceeded,
    non_positive_quantity,
    missing_fields,
    unsupported_currency,
    price_vs_catalog,
    near_threshold,
    due_dates,
    vendor_checks,
    foreign_currency,
]


def validate(invoice: Invoice, conn: sqlite3.Connection, as_of: date) -> list[Finding]:
    """Run every registered rule against one invoice."""
    return check(invoice, Reference.load(conn), as_of)


def check(invoice: Invoice, ref: Reference, as_of: date) -> list[Finding]:
    """Run every rule against pre-loaded reference data (pure)."""
    ctx = Ctx(invoice, ref, as_of)
    return [f for rule in RULES for f in rule(ctx)]
