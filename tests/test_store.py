"""Store transitions: each is one transaction, and a payment interrupted mid-way is never sent twice (D41)."""

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_agents import db, inbox, payment
from invoice_agents.models import EventType, InvoiceKey, Status

KEY = InvoiceKey("Widgets Inc.", "INV-9", 0)


class Crash(BaseException):
    """The process dying: not an Exception, so the bank retry loop does not swallow it."""


def recording_bank(outcome: dict[str, str] | BaseException):
    calls: list[Decimal] = []

    def bank(vendor: str, amount: Decimal) -> dict[str, str]:
        calls.append(amount)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return bank, calls


def crash_after_bank(conn: sqlite3.Connection) -> list[Decimal]:
    db.record(conn, KEY, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED, total="100")
    bank, calls = recording_bank(Crash())
    with pytest.raises(Crash):
        payment.pay(conn, KEY, Decimal(100), "USD", None, "r1", bank)
    return calls


def test_crash_after_bank_call_is_never_paid_again(conn: sqlite3.Connection):
    assert crash_after_bank(conn) == [Decimal(100)]
    assert db.payment_state(conn, KEY) == ("pending", Decimal(100))
    bank, calls = recording_bank({"status": "success"})
    res = payment.pay(conn, KEY, Decimal(100), "USD", None, "r2", bank)
    res2 = payment.pay(conn, KEY, Decimal(100), "USD", None, "r3", bank)
    assert calls == [] and res.status == res2.status == Status.ESCALATED
    assert [r[0] for r in conn.execute("SELECT reason FROM inbox WHERE status='open'")] == [payment.UNCONFIRMED]


def test_reviewer_confirms_an_unconfirmed_payment_without_resending(conn: sqlite3.Connection):
    crash_after_bank(conn)
    payment.pay(conn, KEY, Decimal(100), "USD", None, "r2", recording_bank({"status": "success"})[0])
    out = inbox.resolve(conn, KEY.invoice_number, approve=True, note="seen on statement", reviewer="human:t")
    assert out == {"status": "paid", "amount": "100"} and db.payment_state(conn, KEY) == ("sent", Decimal(100))


def test_reviewer_cancels_then_approves_the_retry_which_pays_once(conn: sqlite3.Connection):
    crash_after_bank(conn)
    payment.pay(conn, KEY, Decimal(100), "USD", None, "r2", recording_bank({"status": "success"})[0])
    out = inbox.resolve(conn, KEY.invoice_number, approve=False, note="not on statement", reviewer="human:t")
    assert out["status"] == "payment_failed" and db.payment_state(conn, KEY) is None
    (item,) = inbox.list_open(conn)
    assert item.reason == "payment_failed"
    inbox.resolve(conn, KEY.invoice_number, approve=True, note="retry", reviewer="human:t")
    assert db.payment_state(conn, KEY) == ("sent", Decimal(100))


def test_failed_payment_and_its_inbox_item_commit_together(conn: sqlite3.Connection):
    conn.execute("CREATE TRIGGER no_inbox BEFORE INSERT ON inbox BEGIN SELECT RAISE(ABORT, 'disk full'); END")
    with pytest.raises(sqlite3.IntegrityError):
        payment.pay(conn, KEY, Decimal(100), "USD", None, "r1", recording_bank({"status": "declined"})[0])
    assert [e["event"] for e in db.events(conn, *KEY[:2])] == []  # no PAYMENT_FAILED without its inbox item
    assert db.payment_state(conn, KEY) == ("pending", Decimal(100))  # the evidence survives the rollback


def test_human_decision_and_inbox_close_commit_together(conn: sqlite3.Connection):
    db.enqueue_inbox(conn, KEY, reason="held", run_id="r", actor="t")
    conn.execute("CREATE TRIGGER no_close BEFORE UPDATE ON inbox BEGIN SELECT RAISE(ABORT, 'locked'); END")
    with pytest.raises(sqlite3.IntegrityError):
        inbox.resolve(conn, KEY.invoice_number, approve=False, note="no", reviewer="human:t")
    assert "human_decision" not in [e["event"] for e in db.events(conn, *KEY[:2])]


def test_old_database_gains_the_payment_status_column(tmp_path: Path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE payments (vendor TEXT, invoice_number TEXT, revision INTEGER, amount_paid TEXT,"
        " currency TEXT, usd_equivalent TEXT, ts TEXT)"
    )
    old.execute("INSERT INTO payments VALUES ('V', 'INV-1', 0, '5', 'USD', '5', 't')")
    old.commit()
    old.close()
    assert db.payment_state(db.connect(path), InvoiceKey("V", "INV-1", 0)) == ("sent", Decimal(5))
