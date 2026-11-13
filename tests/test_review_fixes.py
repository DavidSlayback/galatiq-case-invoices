"""Regressions for the refactor review (R1-R10, D45): recovery, revisions, upgrades and amounts."""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_agents import db, graph, inbox, ledger, payment
from invoice_agents.identity import key_for
from invoice_agents.models import EventType, InvoiceKey, Status
from invoice_agents.normalize import RawExtraction, to_invoice
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT


class Crash(BaseException):
    """The process dying mid-call."""


def crash(vendor: str, amount: Decimal) -> dict[str, str]:
    raise Crash


def declined(vendor: str, amount: Decimal) -> dict[str, str]:
    return {"status": "declined"}


def age_pending(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("UPDATE payments SET ts='2000-01-01T00:00:00' WHERE status='pending'")


def test_r1_a_payment_a_dead_process_left_pending_reaches_the_inbox(conn: sqlite3.Connection, offline: Settings):
    with pytest.raises(Crash):
        graph.process_sync(INVOICES / "invoice_1004.json", offline, conn, bank=crash)
    age_pending(conn)
    again = graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    assert again.status == Status.DUPLICATE_SKIPPED  # re-running the file never pays...
    (item,) = inbox.list_open(conn)  # ...but the sweep has surfaced the stuck payment
    assert item.reason == "payment_unconfirmed" and item.amount_due == "1890.00"


def test_r1_a_live_payment_is_not_swept(conn: sqlite3.Connection):
    key = InvoiceKey("Widgets Inc.", "INV-5", 0)
    db.start_payment(conn, key, Decimal(5), "USD", Decimal(5))
    assert inbox.list_open(conn) == []  # started moments ago: its process may still be talking to the bank


def test_r2_a_revision_keeps_the_unconfirmed_item_open(conn: sqlite3.Connection, offline: Settings):
    with pytest.raises(Crash):
        graph.process_sync(INVOICES / "invoice_1004.json", offline, conn, bank=crash)
    age_pending(conn)
    graph.process_sync(INVOICES / "invoice_1004_revised.json", offline, conn)
    reasons = sorted(i.reason for i in inbox.list_open(conn))
    assert reasons == ["payment_unconfirmed", "revision_after_payment"]


def test_r3_a_database_from_before_d40_is_refused(tmp_path: Path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE invoices (vendor TEXT COLLATE NOCASE, invoice_number TEXT COLLATE NOCASE)")
    old.commit()
    old.close()
    with pytest.raises(RuntimeError, match=r"main\.py reset"):
        db.connect(path)


def test_r5_case_and_spacing_copies_are_duplicates(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    g = json.loads((ROOT / "fixtures/golden/extract/invoice_1004_json.json").read_text())
    shouted = to_invoice(RawExtraction.model_validate(g["output"] | {"vendor": "PRECISION  PARTS LTD."}))
    assert isinstance(ledger.check(conn, key_for(conn, shouted, "c" * 64), shouted), ledger.Duplicate)


def test_r8_a_failed_revision_delta_reports_the_delta(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    graph.process_sync(INVOICES / "invoice_1004_revised.json", offline, conn)
    out = inbox.resolve(conn, "INV-1004", approve=True, note="ok", reviewer="human:t", bank=declined)
    assert out == {"status": "payment_failed", "amount": "4050.00"}


def test_r10_an_alias_name_finds_the_inbox_item(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    out = inbox.resolve(conn, "1012", approve=False, note="no", reviewer="human:t", vendor="QuickShip Distributers")
    assert out == {"status": "rejected"}


def test_r11_a_late_bank_success_after_cancel_is_never_sent_again(conn: sqlite3.Connection):
    """The sweep flags a slow call, a reviewer cancels, then the bank answers success."""
    key = InvoiceKey("Widgets Inc.", "INV-6", 0)
    db.record(conn, key, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED, total="100")
    sent: list[Decimal] = []

    def slow_bank(vendor: str, amount: Decimal) -> dict[str, str]:
        sent.append(amount)
        age_pending(conn)
        assert [i.reason for i in inbox.list_open(conn)] == ["payment_unconfirmed"]  # the sweep flags the live call
        inbox.resolve(conn, "INV-6", approve=False, note="not on statement yet", reviewer="human:t")
        return {"status": "success"}  # and then the money leaves after all

    payment.pay(conn, key, Decimal(100), "USD", None, "r1", slow_bank)
    assert db.payment_state(conn, key) == ("sent", Decimal(100)) and inbox.list_open(conn) == []
    assert payment.pay(conn, key, Decimal(100), "USD", None, "r2", slow_bank).amount == Decimal(0)
    assert sent == [Decimal(100)]


def test_r12_a_refusal_after_the_sweep_leaves_no_orphan_item(conn: sqlite3.Connection):
    key = InvoiceKey("Widgets Inc.", "INV-7", 0)

    def flagged_then_declined(vendor: str, amount: Decimal) -> dict[str, str]:
        age_pending(conn)
        inbox.list_open(conn)
        return {"status": "declined"}

    payment.pay(conn, key, Decimal(100), "USD", None, "r1", flagged_then_declined)
    assert [i.reason for i in inbox.list_open(conn)] == ["payment_failed"]
