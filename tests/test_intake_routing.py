"""Ledger intake and routing tested through their own interfaces, with no graph and no monkeypatching."""

import sqlite3
from datetime import date
from decimal import Decimal

from invoice_agents import approval, db, identity, ledger, reconcile
from invoice_agents.approval import AutoApprove, HumanReview, Reject
from invoice_agents.models import Finding, Invoice, LineItem

SRC = {"path": "a.json", "sha256": "a" * 64, "format": "json"}


def inv(total: str = "250", revision: int = 0) -> Invoice:
    return Invoice(
        vendor="Widgets Inc.", invoice_number="INV-7200", invoice_date=date(2026, 1, 15), total=Decimal(total),
        revision=revision,
        lines=[LineItem(item_raw="WidgetA", sku="WidgetA", quantity=Decimal(1), unit_price=Decimal(total))],
    )  # fmt: skip


def test_route_sends_any_revision_after_payment_to_a_person():
    assert isinstance(approval.route(inv(), [], Decimal(250)), AutoApprove)
    r = approval.route(inv(), [], Decimal(250), amount_due=Decimal(50))
    assert isinstance(r, HumanReview) and r.reason == approval.REVISION_AFTER_PAYMENT


def test_route_still_rejects_hard_findings_before_the_revision_check():
    hard = reconcile.mismatch_finding(["total off by 1.00"], attempts=3)
    assert isinstance(approval.route(inv(), [hard], Decimal(250), amount_due=Decimal(50)), Reject)


def test_intake_records_a_new_invoice_and_skips_its_copy(conn: sqlite3.Connection):
    key = identity.key_for(conn, inv(), SRC["sha256"])
    first = ledger.intake(conn, key, inv(), source=SRC, run_id="r1", extracted={})
    copy = ledger.intake(conn, key, inv(), source={**SRC, "path": "a.txt"}, run_id="r2", extracted={})
    assert first.skipped is None and copy.skipped is not None and copy.verdict == "Duplicate"
    row = db.invoice_row(conn, key.vendor, key.invoice_number)
    assert row is not None and row["source_path"] == "a.json"  # the copy did not take over the row


def test_intake_of_a_paid_invoice_revision_reports_what_is_owed(conn: sqlite3.Connection):
    key = identity.key_for(conn, inv(), SRC["sha256"])
    ledger.intake(conn, key, inv(), source=SRC, run_id="r1", extracted={})
    attempt = db.start_payment(conn, key, Decimal(250), "USD", Decimal(250))
    assert attempt == 1
    db.settle_payment(conn, key, attempt, run_id="r1", actor="t", payload={})
    rev = inv(total="400", revision=1)
    out = ledger.intake(conn, key._replace(revision=1), rev, source=SRC, run_id="r2", extracted={})
    assert out.verdict == "Revision" and out.amount_due == Decimal(150)


def test_conflicting_copy_gets_its_own_key_and_a_fraud_finding(conn: sqlite3.Connection):
    key = identity.key_for(conn, inv(), SRC["sha256"])
    ledger.intake(conn, key, inv(), source=SRC, run_id="r1", extracted={})
    out = ledger.intake(conn, key, inv(total="900"), source={**SRC, "sha256": "b" * 64}, run_id="r2", extracted={})
    assert out.key != key and identity.same_invoice(out.key.invoice_number, key.invoice_number)
    assert [f.rule_id for f in out.findings] == ["DUPLICATE_NUMBER_CONFLICT"]
    assert isinstance(out.findings[0], Finding)
