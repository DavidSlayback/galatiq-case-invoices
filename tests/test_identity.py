"""Invoice identity: one folding rule in Python and SQL, registry resolution, conflict copies."""

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from invoice_agents import db, identity, ledger, payment
from invoice_agents.cli import app
from invoice_agents.models import EventType, Invoice, InvoiceKey, LineItem, Status


def OK(vendor: str, amount: Decimal) -> dict[str, str]:
    return {"status": "success"}


def inv(vendor: str, number: str = "INV-7100") -> Invoice:
    return Invoice(
        vendor=vendor, invoice_number=number, invoice_date=date(2026, 1, 15), total=Decimal(250),
        lines=[LineItem(item_raw="WidgetA", sku="WidgetA", quantity=Decimal(1), unit_price=Decimal(250))],
    )  # fmt: skip


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Müller GmbH", "MÜLLER  GMBH"),
        ("Straße AG", "STRASSE AG"),
        ("\uff37\uff49\uff44\uff47\uff45\uff54\uff53 Inc.", "widgets inc."),  # full-width
        ("ΣΟΦΙΑ", "σοφια"),
    ],
)
def test_fold_equates_unicode_case_and_width(a: str, b: str):
    assert identity.fold(a) == identity.fold(b)


def test_sql_columns_compare_with_the_same_fold(conn: sqlite3.Connection):
    db.record(
        conn, InvoiceKey("Müller GmbH", "INV-1"), EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED
    )
    assert db.invoice_row(conn, "MÜLLER GMBH", "inv-1") is not None


def _pay_first(conn: sqlite3.Connection, vendor: str) -> InvoiceKey:
    first = identity.key_for(conn, inv(vendor), "a" * 64)
    db.record(conn, first, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED,
              core=__import__("json").dumps(ledger.core(inv(vendor))))  # fmt: skip
    payment.pay(conn, first, Decimal(250), "USD", None, "r", OK)
    return first


def test_non_ascii_case_variant_is_not_paid_twice(conn: sqlite3.Connection):
    _pay_first(conn, "Müller GmbH")
    again = identity.key_for(conn, inv("MÜLLER GMBH"), "b" * 64)
    assert isinstance(ledger.check(conn, again, inv("MÜLLER GMBH")), ledger.Duplicate | ledger.Conflict)
    assert ledger.already_paid(conn, again.vendor, again.invoice_number) == Decimal(250)


def test_alias_resolves_to_the_registered_vendor(conn: sqlite3.Connection):
    key = identity.key_for(conn, inv("QuickShip  Distributers"), "a" * 64)
    assert key.vendor == "FastShip Ltd."


def test_resubmission_under_an_alias_meets_the_original(conn: sqlite3.Connection):
    _pay_first(conn, "FastShip Ltd.")
    again = identity.key_for(conn, inv("QuickShip Distributors"), "b" * 64)
    assert ledger.already_paid(conn, again.vendor, again.invoice_number) == Decimal(250)
    assert not isinstance(ledger.check(conn, again, inv("QuickShip Distributors")), ledger.New)


def test_lookalike_is_never_resolved_to_the_real_vendor(conn: sqlite3.Connection):
    assert identity.key_for(conn, inv("Widgets lnc."), "a" * 64).vendor == "Widgets lnc."


def test_conflict_copy_shares_payments_but_wildcards_do_not(conn: sqlite3.Connection):
    k = InvoiceKey("Widgets Inc.", "INV-1", 0)
    payment.pay(conn, k, Decimal(1000), "USD", None, "r", OK)
    payment.pay(conn, InvoiceKey("Widgets Inc.", "INV-10", 0), Decimal(7), "USD", None, "r", OK)
    assert ledger.already_paid(conn, k.vendor, identity.conflict_key(k, "f" * 64).invoice_number) == Decimal(1000)
    assert ledger.already_paid(conn, k.vendor, "INV-1%") == Decimal(0)  # no LIKE wildcard


@pytest.mark.parametrize("raw", ["inv 1004", "1004", "INV-1004", " Invoice #1004 "])
def test_typed_numbers_find_the_ledger_number(raw: str):
    assert identity.lookup_number(raw) == "INV-1004"


def test_history_accepts_a_loosely_typed_number(tmp_path: Path):
    dbp = str(tmp_path / "h.db")
    runner = CliRunner()
    runner.invoke(app, ["--invoice_path=data/invoices/invoice_1004.json", "--offline", "--db", dbp])
    r = runner.invoke(app, ["history", "inv 1004", "--db", dbp])
    assert r.exit_code == 0 and "received" in r.output
