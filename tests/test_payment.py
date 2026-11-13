import json
import sqlite3
from decimal import Decimal

from invoice_agents import db, graph, ledger, payment
from invoice_agents.models import InvoiceKey, Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES

KEY = InvoiceKey("Widgets Inc.", "INV-1", 0)


def calls_recorder(result: dict[str, str] | Exception):
    calls: list[tuple[str, Decimal]] = []

    def bank(vendor: str, amount: Decimal) -> dict[str, str]:
        calls.append((vendor, amount))
        if isinstance(result, Exception):
            raise result
        return result

    return bank, calls


def test_second_pay_of_same_revision_is_a_no_op(conn: sqlite3.Connection):
    bank, calls = calls_recorder({"status": "success"})
    first = payment.pay(conn, KEY, Decimal("100"), "USD", Decimal("100"), "r1", bank)
    second = payment.pay(conn, KEY, Decimal("100"), "USD", Decimal("100"), "r2", bank)
    assert (first.amount, second.amount) == (Decimal("100"), Decimal("0")) and len(calls) == 1
    evts = [e["event"] for e in db.events(conn, *KEY[:2])]
    assert evts == ["paid", "payment_skipped_already_paid"]


def test_revision_pays_only_the_difference(conn: sqlite3.Connection):
    bank, calls = calls_recorder({"status": "success"})
    payment.pay(conn, KEY, Decimal("1890.00"), "USD", None, "r1", bank)
    payment.pay(conn, KEY._replace(revision=1), Decimal("5940.00"), "USD", None, "r2", bank)
    assert [a for _, a in calls] == [Decimal("1890.00"), Decimal("4050.00")]
    assert ledger.already_paid(conn, KEY.vendor, KEY.invoice_number) == Decimal("5940.00")


def test_refusals_retry_then_escalate(conn: sqlite3.Connection):
    bank, calls = calls_recorder({"status": "declined"})
    res = payment.pay(conn, KEY, Decimal("100"), "USD", None, "r1", bank)
    assert res.status == Status.PAYMENT_FAILED and len(calls) == payment.ATTEMPTS == 2
    assert conn.execute("SELECT reason FROM inbox").fetchone()[0] == "payment_failed"
    assert db.payment_state(conn, KEY) == ("cancelled", Decimal("100"))  # kept, but never counted as paid


def test_an_exception_is_ambiguous_so_it_is_never_retried(conn: sqlite3.Connection):
    bank, calls = calls_recorder(TimeoutError("no reply"))
    res = payment.pay(conn, KEY, Decimal("100"), "USD", None, "r1", bank)
    assert res.status == Status.ESCALATED and len(calls) == 1
    assert conn.execute("SELECT reason FROM inbox").fetchone()[0] == payment.UNCONFIRMED
    assert db.payment_state(conn, KEY) == ("pending", Decimal("100"))  # the evidence is kept


def test_eur_paid_in_invoice_currency_with_usd_recorded(conn: sqlite3.Connection):
    bank, _ = calls_recorder({"status": "success"})
    payment.pay(conn, KEY, Decimal("4125.00"), "EUR", Decimal("4455.00"), "r1", bank)
    row = conn.execute("SELECT amount_paid, currency, usd_equivalent FROM payments").fetchone()
    assert tuple(row) == ("4125.00", "EUR", "4455.00")


def test_rejection_names_bad_lines(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1016.json", offline, conn)
    ev = db.events(conn, "Widgets Inc.", "INV-1016")[-1]
    assert ev["event"] == "rejected" and json.loads(ev["payload"])["bad_lines"] == ["WidgetC"]


def test_bank_failure_through_the_graph_goes_to_the_inbox(conn: sqlite3.Connection, offline: Settings):
    bank, calls = calls_recorder({"status": "declined"})
    o = graph.process_sync(INVOICES / "invoice_1004.json", offline, conn, bank=bank)
    assert o.status == Status.PAYMENT_FAILED and len(calls) == payment.ATTEMPTS
    assert conn.execute("SELECT reason FROM inbox").fetchone()[0] == "payment_failed"
