"""Regressions for the refactor review (R1-R16, D45): recovery, revisions, upgrades, amounts and late bank answers."""

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
from tests.conftest import INVOICES, ROOT, Crash, declined


def crash(vendor: str, amount: Decimal) -> dict[str, str]:
    raise Crash


def age_pending(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("UPDATE payments SET ts='2000-01-01T00:00:00' WHERE status='pending'")


def test_r1_a_payment_a_dead_process_left_pending_reaches_the_inbox(conn: sqlite3.Connection, offline: Settings):
    """The process dies mid-payment; re-running the file is a duplicate, so only the sweep can surface it."""
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
    """The sweep flags a live call, then the bank declines: only the retry item stays open."""
    key = InvoiceKey("Widgets Inc.", "INV-7", 0)

    def flagged_then_declined(vendor: str, amount: Decimal) -> dict[str, str]:
        age_pending(conn)
        inbox.list_open(conn)
        return {"status": "declined"}

    payment.pay(conn, key, Decimal(100), "USD", None, "r1", flagged_then_declined)
    assert [i.reason for i in inbox.list_open(conn)] == ["payment_failed"]


def test_r13_a_payment_another_process_holds_never_calls_the_bank(conn: sqlite3.Connection):
    """Two processes race to claim one payment row; the loser gets no attempt number."""
    key = InvoiceKey("Widgets Inc.", "INV-8", 0)
    assert db.start_payment(conn, key, Decimal(100), "USD", Decimal(100)) == 1  # the other process
    assert db.start_payment(conn, key, Decimal(100), "USD", Decimal(100)) is None  # this one: refused


def test_r14_a_late_success_after_the_retry_is_recorded_as_an_overpayment(conn: sqlite3.Connection):
    """Live call flagged and cancelled, retry approved and sent, then the first call succeeds."""
    key = InvoiceKey("Widgets Inc.", "INV-9", 0)
    db.record(conn, key, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED, total="100")
    sent: list[Decimal] = []

    def ok(vendor: str, amount: Decimal) -> dict[str, str]:
        sent.append(amount)
        return {"status": "success"}

    def slow_bank(vendor: str, amount: Decimal) -> dict[str, str]:
        sent.append(amount)
        age_pending(conn)
        inbox.list_open(conn)
        inbox.resolve(conn, "INV-9", approve=False, note="not there", reviewer="human:t")
        inbox.resolve(conn, "INV-9", approve=True, note="retry", reviewer="human:t", bank=ok)  # send 2
        return {"status": "success"}  # send 1 lands late

    payment.pay(conn, key, Decimal(100), "USD", None, "r1", slow_bank)
    assert sent == [Decimal(100), Decimal(100)]
    assert ledger.already_paid(conn, key.vendor, key.invoice_number) == Decimal(200)  # the ledger tells the truth
    assert [i.reason for i in inbox.list_open(conn)] == ["overpayment"]
    out = inbox.resolve(conn, "INV-9", approve=True, note="vendor refunding 100", reviewer="human:t", bank=ok)
    assert out == {"status": "recovery_recorded", "amount": "100"} and sent == [Decimal(100), Decimal(100)]
    assert db.invoice_row(conn, key.vendor, key.invoice_number)["status"] == "paid"  # pyright: ignore[reportOptionalSubscript]


def test_r15_a_late_success_after_a_declined_retry_is_not_an_overpayment(conn: sqlite3.Connection):
    """Call flagged and cancelled, retry approved but declined, then the first call succeeds."""
    key = InvoiceKey("Widgets Inc.", "INV-10", 0)
    db.record(conn, key, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED, total="100")

    def slow_bank(vendor: str, amount: Decimal) -> dict[str, str]:
        age_pending(conn)
        inbox.list_open(conn)
        inbox.resolve(conn, "INV-10", approve=False, note="not there", reviewer="human:t")
        inbox.resolve(conn, "INV-10", approve=True, note="retry", reviewer="human:t", bank=declined)
        return {"status": "success"}  # attempt 1 lands; attempt 2 was declined, so this is the only send

    payment.pay(conn, key, Decimal(100), "USD", None, "r1", slow_bank)
    assert db.payment_state(conn, key) == ("sent", Decimal(100))
    assert ledger.already_paid(conn, key.vendor, key.invoice_number) == Decimal(100)
    assert inbox.list_open(conn) == []  # no false clawback, no stale retry


def test_r16_a_late_success_while_the_retry_is_pending_then_declined_is_the_only_send(conn: sqlite3.Connection):
    """Attempt 1 lands late while retry 2 is pending; once 2 is declined, attempt 1 is the payment."""
    key = InvoiceKey("Widgets Inc.", "INV-11", 0)
    amt = {"amount": Decimal(100)}
    first = db.start_payment(conn, key, Decimal(100), "USD", Decimal(100))
    assert first == 1
    db.fail_payment(conn, key, first, run_id="r", actor="human:t", amount=Decimal(100), payload=amt)
    retry = db.start_payment(conn, key, Decimal(100), "USD", Decimal(100))
    assert retry == 2
    db.settle_payment(conn, key, first, run_id="r", actor="payment", payload=amt)  # attempt 1 lands late
    db.settle_payment(conn, key, first, run_id="r", actor="payment", payload=amt)  # reported twice
    assert sorted(i.reason for i in inbox.list_open(conn)) == ["overpayment", "payment_failed"]
    assert ledger.already_paid(conn, key.vendor, key.invoice_number) == Decimal(200)  # pending retry + late send
    db.fail_payment(conn, key, retry, run_id="r", actor="payment", amount=Decimal(100), payload=amt)
    assert db.payment_state(conn, key) == ("sent", Decimal(100))
    assert ledger.already_paid(conn, key.vendor, key.invoice_number) == Decimal(100)
    assert inbox.list_open(conn) == []  # no false clawback, no stale retry


def test_r17_a_skipped_rerun_does_not_postpone_recovery(conn: sqlite3.Connection, offline: Settings):
    """Re-running a file inside the bound is a duplicate, and must not restart the 30-minute clock."""
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    with conn:
        conn.execute("UPDATE invoices SET updated_at='2026-01-01T00:00:00.000+00:00'")
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)  # duplicate: RECEIVED + DUPLICATE_SKIPPED
    assert conn.execute("SELECT updated_at FROM invoices").fetchone()[0] == "2026-01-01T00:00:00.000+00:00"


def test_r17_an_invoice_a_crash_left_after_its_decision_is_resumed_by_a_rerun(
    conn: sqlite3.Connection, offline: Settings, monkeypatch: pytest.MonkeyPatch
):
    """DECIDED is written, then the process dies before payment starts; re-running the file finishes it."""
    from invoice_agents import settle

    def dies(*_: object) -> None:
        raise Crash

    monkeypatch.setattr(settle.payment, "pay", dies)  # dies right after DECIDED
    with pytest.raises(Crash):
        graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    monkeypatch.undo()
    assert graph.process_sync(INVOICES / "invoice_1004.json", offline, conn).status == Status.DUPLICATE_SKIPPED
    with conn:  # nothing has moved for longer than any live run can take
        conn.execute("UPDATE invoices SET updated_at='2000-01-01T00:00:00'")
    again = graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    assert again.status == Status.PAID and db.payment_state(conn, again.key) == ("sent", Decimal("1890.00"))


def test_r18_a_resumed_revision_of_a_paid_invoice_still_goes_to_a_person(
    conn: sqlite3.Connection, offline: Settings, monkeypatch: pytest.MonkeyPatch
):
    """R1 of a paid invoice crashes after intake; the resumed run must not auto-pay the difference."""
    from invoice_agents import approval

    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)

    def dies(*_: object, **__: object) -> None:
        raise Crash

    monkeypatch.setattr(approval, "route", dies)
    with pytest.raises(Crash):
        graph.process_sync(INVOICES / "invoice_1004_revised.json", offline, conn)
    monkeypatch.undo()
    with conn:
        conn.execute("UPDATE invoices SET updated_at='2000-01-01T00:00:00'")
    again = graph.process_sync(INVOICES / "invoice_1004_revised.json", offline, conn)
    assert again.status == Status.ESCALATED
    assert [i.reason for i in inbox.list_open(conn)] == ["revision_after_payment"]


def test_r19_a_recent_unfinished_invoice_is_left_to_its_live_run(conn: sqlite3.Connection, offline: Settings):
    """Two minutes is not dead: an invoice mid-review stays a duplicate until the run bound passes."""
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    with conn:
        conn.execute("UPDATE invoices SET status='validated', updated_at=?", (db.now(),))
        conn.execute("DELETE FROM payments")
    assert graph.process_sync(INVOICES / "invoice_1004.json", offline, conn).status == Status.DUPLICATE_SKIPPED


def test_r20_a_human_decision_a_crash_left_unsettled_goes_back_to_the_person(
    conn: sqlite3.Connection, offline: Settings, monkeypatch: pytest.MonkeyPatch
):
    """A person rejects, the process dies before REJECTED: a re-run must never re-judge (and maybe pay) it."""
    from invoice_agents import approval, settle

    def escalate(inv: object, f: object, usd: object, due: object = None) -> object:
        return approval.HumanReview(inv, f, usd, reason="held")  # type: ignore[arg-type]

    monkeypatch.setattr(approval, "route", escalate)
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    monkeypatch.undo()
    (item,) = inbox.list_open(conn)

    def dies(*_: object, **__: object) -> None:
        raise Crash

    monkeypatch.setattr(settle, "settle", dies)
    with pytest.raises(Crash):
        inbox.resolve(conn, "INV-1004", approve=False, note="fake vendor", reviewer="human:t", inbox_id=item.id)
    monkeypatch.undo()
    with conn:
        conn.execute("UPDATE invoices SET updated_at='2000-01-01T00:00:00'")
    again = graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    assert again.status == Status.DUPLICATE_SKIPPED and db.payment_state(conn, item.key) is None
    (back,) = inbox.list_open(conn)
    assert back.reason == "decision_unsettled"
    assert inbox.resolve(conn, "INV-1004", approve=False, note="still fake", reviewer="human:t") == {
        "status": "rejected"
    }


def test_r21_a_quick_rerun_does_not_hide_an_unsettled_human_decision(
    conn: sqlite3.Connection, offline: Settings, monkeypatch: pytest.MonkeyPatch
):
    """A re-run inside the sweep window writes received + duplicate_skipped after the person's decision."""
    from invoice_agents import approval, settle

    def escalate(inv: object, f: object, usd: object, due: object = None) -> object:
        return approval.HumanReview(inv, f, usd, reason="held")  # type: ignore[arg-type]

    monkeypatch.setattr(approval, "route", escalate)
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    monkeypatch.undo()
    (item,) = inbox.list_open(conn)

    def dies(*_: object, **__: object) -> None:
        raise Crash

    monkeypatch.setattr(settle, "settle", dies)
    with pytest.raises(Crash):
        inbox.resolve(conn, "INV-1004", approve=False, note="fake vendor", reviewer="human:t", inbox_id=item.id)
    monkeypatch.undo()
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)  # right away: skipped as a duplicate
    with conn:
        conn.execute("UPDATE invoices SET updated_at='2000-01-01T00:00:00'")
    assert [i.reason for i in inbox.list_open(conn)] == ["decision_unsettled"]
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    assert db.payment_state(conn, item.key) is None  # never paid what a person rejected
