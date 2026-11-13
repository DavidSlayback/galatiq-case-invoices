"""Settlement: the same guardrail, events and payment whoever decided (D42)."""

import sqlite3
from decimal import Decimal

import pytest

from invoice_agents import db, inbox, settle
from invoice_agents.models import Decision, EventType, Finding, InvoiceKey, Status
from tests.conftest import ok

KEY = InvoiceKey("Widgets Inc.", "INV-8", 0)
STOCK = Finding(rule_id="STOCK_EXCEEDED", severity="hard", message="too many", evidence={"sku": "GadgetX"})


def events(conn: sqlite3.Connection) -> list[str]:
    return [e["event"] for e in db.events(conn, *KEY[:2])]


def test_reject_records_decision_and_bad_lines(conn: sqlite3.Connection):
    d = Decision(kind="reject", actor="human:t", reasons=["no"])
    out = settle.settle(conn, KEY, d, findings=[STOCK], total=Decimal(10), currency="USD", usd_total=None, run_id="r")
    assert out.status == Status.REJECTED and events(conn) == ["decided", "rejected"]
    assert '"bad_lines": ["GadgetX"]' in db.events(conn, *KEY[:2])[-1]["payload"]


def test_approval_with_a_hard_finding_is_rejected_by_the_guardrail(conn: sqlite3.Connection):
    d = Decision(kind="approve", actor="vp_agent")
    out = settle.settle(conn, KEY, d, findings=[STOCK], total=Decimal(10), currency="USD", usd_total=None,
                        run_id="r", bank=ok)  # fmt: skip
    assert out.status == Status.REJECTED and out.decision.actor == "guardrail"
    assert events(conn) == ["guardrail_override", "decided", "rejected"]


def test_approval_pays_once_and_records_decided(conn: sqlite3.Connection):
    d = Decision(kind="approve", actor="rules")
    out = settle.settle(conn, KEY, d, findings=[], total=Decimal(10), currency="USD", usd_total=None, run_id="r",
                        bank=ok)  # fmt: skip
    assert (out.status, out.amount_paid) == (Status.PAID, Decimal(10)) and events(conn) == ["decided", "paid"]


def test_approval_without_a_total_is_refused(conn: sqlite3.Connection):
    with pytest.raises(ValueError, match="no total"):
        settle.settle(conn, KEY, Decision(kind="approve", actor="h"), findings=[], total=None, currency="USD",
                      usd_total=None, run_id="r")  # fmt: skip
    assert events(conn) == []


def test_human_reject_leaves_the_same_trail_as_the_graph(conn: sqlite3.Connection):
    db.record(conn, KEY, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED, total="10")
    db.enqueue_inbox(conn, KEY, reason="held", run_id="r", actor="t")
    inbox.resolve(conn, KEY.invoice_number, approve=False, note="duplicate of a paper invoice", reviewer="human:t")
    assert events(conn)[-3:] == ["human_decision", "decided", "rejected"]
