import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from invoice_agents.models import Invoice, LineItem
from invoice_agents.rules import Reference, check
from invoice_agents.settings import DEFAULT_AS_OF


@pytest.fixture
def ref(conn: sqlite3.Connection) -> Reference:
    return Reference.load(conn)


def line(sku: str | None, qty: str, price: str, raw: str | None = None) -> LineItem:
    return LineItem(item_raw=raw or sku or "?", sku=sku, quantity=Decimal(qty), unit_price=Decimal(price))


def inv(**kw: Any) -> Invoice:
    base: dict[str, Any] = {
        "vendor": "Widgets Inc.",
        "invoice_number": "INV-T",
        "invoice_date": date(2026, 1, 15),
        "due_date": date(2026, 2, 14),
        "payment_terms": "Net 30",
        "lines": [line("WidgetA", "1", "250.00")],
        "subtotal": Decimal("250.00"),
        "total": Decimal("250.00"),
    }
    return Invoice(**{**base, **kw})


def ids(i: Invoice, ref: Reference, as_of: date = DEFAULT_AS_OF) -> list[str]:
    return [f.rule_id for f in check(i, ref, as_of)]


def test_clean_invoice_has_no_findings(ref: Reference):
    assert ids(inv(), ref) == []


# One case per rule ID: (rule_id, invoice overrides).
CASES: list[tuple[str, dict[str, Any]]] = [
    ("UNKNOWN_ITEM", {"lines": [line(None, "3", "350", raw="WidgetC")]}),
    ("ZERO_STOCK_ITEM", {"lines": [line("FakeItem", "100", "1000")]}),
    ("STOCK_EXCEEDED", {"lines": [line("GadgetX", "20", "750")]}),
    ("NEGATIVE_QUANTITY", {"lines": [line("WidgetA", "-5", "250")]}),
    ("NEGATIVE_QUANTITY", {"lines": [line("WidgetA", "0", "250")]}),
    ("MISSING_VENDOR", {"vendor": ""}),
    ("MISSING_DUE_DATE", {"due_date": None}),
    ("MISSING_TOTAL", {"total": None}),
    ("NO_LINE_ITEMS", {"lines": []}),
    ("UNSUPPORTED_CURRENCY", {"currency": "JPY"}),
    ("PRICE_OVER_CATALOG", {"lines": [line("WidgetA", "4", "300", raw="WidgetA (rush order)")]}),
    ("NEAR_THRESHOLD", {"total": Decimal("9500")}),
    ("DUE_BEFORE_INVOICE", {"due_date": date(2026, 1, 15)}),
    ("DUE_TERMS_MISMATCH", {"due_date": date(2026, 2, 16)}),
    ("PAST_DUE", {"due_date": date(2026, 1, 31), "payment_terms": None}),
    ("DATE_UNPARSEABLE", {"due_date": None, "due_date_raw": "yesterday"}),
    ("UNKNOWN_VENDOR", {"vendor": "NoProd Industries"}),
    ("URGENCY_LANGUAGE", {"notes": "URGENT - pay now"}),
    ("UNKNOWN_VENDOR_PRESSURE", {"vendor": "Fraudster LLC", "notes": "Wire transfer preferred"}),
    ("SUSPICIOUS_ADDRESS", {"vendor_address": "1600 Pennsylvania Ave, Washington, DC 20500"}),
    ("FOREIGN_CURRENCY", {"currency": "EUR"}),
    ("DISCOUNT_APPLIED", {"lines": [line("WidgetA", "5", "240")]}),
]


@pytest.mark.parametrize(("rule_id", "overrides"), CASES, ids=[c[0] for c in CASES])
def test_each_rule_fires(ref: Reference, rule_id: str, overrides: dict[str, Any]):
    assert rule_id in ids(inv(**overrides), ref)


@pytest.mark.parametrize(
    ("total", "fires"),
    [("9499.99", False), ("9500", True), ("9999.99", True), ("10000", False)],
)
def test_near_threshold_boundaries(ref: Reference, total: str, fires: bool):
    assert ("NEAR_THRESHOLD" in ids(inv(total=Decimal(total)), ref)) is fires


@pytest.mark.parametrize(("due", "fires"), [(date(2026, 2, 15), False), (date(2026, 2, 16), True)])
def test_terms_tolerance_is_one_day(ref: Reference, due: date, fires: bool):
    # Net 30 from Jan 15 is Feb 14; +1 day is tolerated (D26), +2 is not.
    assert ("DUE_TERMS_MISMATCH" in ids(inv(due_date=due), ref)) is fires


def test_due_on_as_of_is_not_past_due(ref: Reference):
    assert "PAST_DUE" not in ids(inv(due_date=DEFAULT_AS_OF, payment_terms=None), ref)


def test_1013_sums_split_lines(ref: Reference):
    lines = [
        line("WidgetA", "15", "250"), line("WidgetB", "10", "500"), line("GadgetX", "5", "750"),
        line("WidgetA", "5", "240"), line("WidgetB", "8", "480"), line("GadgetX", "3", "750"),
        line("WidgetA", "2", "250"), line("GadgetX", "1", "750"),
    ]  # fmt: skip
    found = check(inv(lines=lines), ref, DEFAULT_AS_OF)
    assert sorted(f.evidence["sku"] for f in found if f.rule_id == "STOCK_EXCEEDED") == [
        "GadgetX",
        "WidgetA",
        "WidgetB",
    ]
    assert {f.evidence["invoiced"] for f in found if f.rule_id == "STOCK_EXCEEDED"} == {"22", "18", "9"}


def test_1010_flags_only_the_rush_line(ref: Reference):
    lines = [
        line("WidgetA", "8", "250"), line("WidgetB", "4", "500"), line("GadgetX", "2", "750"),
        line("WidgetA", "4", "300", raw="WidgetA (rush order)"),
    ]  # fmt: skip
    found = [f for f in check(inv(lines=lines), ref, DEFAULT_AS_OF) if f.rule_id == "PRICE_OVER_CATALOG"]
    assert [f.evidence["item"] for f in found] == ["WidgetA (rush order)"]


def test_1014_eur_has_only_notes(ref: Reference):
    i = inv(
        vendor="TechParts International", currency="EUR", invoice_date=date(2026, 1, 26),
        due_date=date(2026, 2, 26), lines=[line("WidgetA", "4", "225"), line("WidgetB", "6", "475")],
        total=Decimal("4125.00"),
    )  # fmt: skip
    found = check(i, ref, DEFAULT_AS_OF)
    assert {f.severity for f in found} == {"note"}
    assert {f.rule_id for f in found} == {"FOREIGN_CURRENCY", "DISCOUNT_APPLIED"}


def test_unknown_vendor_alone_is_soft_not_fraud(ref: Reference):
    found = check(inv(vendor="NoProd Industries"), ref, DEFAULT_AS_OF)
    assert {(f.rule_id, f.severity) for f in found} == {("UNKNOWN_VENDOR", "soft"), ("VENDOR_RISK", "note")}
