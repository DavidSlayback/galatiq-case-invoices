import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from invoice_agents import db, graph, inbox
from invoice_agents.cli import app
from invoice_agents.models import Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES


def test_1012_approved_by_human_is_paid(conn: sqlite3.Connection, offline: Settings):
    assert graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn).status == Status.ESCALATED
    (item,) = inbox.list_open(conn)
    assert item.reason == "vendor_change" and "VENDOR_RENAMED" in item.flags and item.risk == 20
    assert item.reasoning  # the reviewer sees why the agents could not settle it
    res = inbox.resolve(
        conn, "INV-1012", approve=True, note="Confirmed rename with FastShip by phone", reviewer="human:t"
    )
    assert res == {"status": "paid", "amount": "9975.00"}
    # The alias is keyed under the registered vendor, so the payment goes to FastShip's record.
    evts = [e["event"] for e in db.events(conn, "FastShip Ltd.", "INV-1012")]
    assert evts[-2:] == ["human_decision", "paid"] and inbox.list_open(conn) == []


def test_revision_delta_approval_pays_only_the_delta(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    graph.process_sync(INVOICES / "invoice_1004_revised.json", offline, conn)
    res = inbox.resolve(conn, "INV-1004", approve=True, note="PO amendment confirmed", reviewer="human:t")
    assert res == {"status": "paid", "amount": "4050.00"}
    assert [r[0] for r in conn.execute("SELECT amount_paid FROM payments ORDER BY rowid")] == ["1890.00", "4050.00"]


def test_reject_with_note(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    assert (
        inbox.resolve(conn, "INV-1012", approve=False, note="Rename not confirmed", reviewer="h")["status"]
        == "rejected"
    )
    assert conn.execute("SELECT count(*) FROM payments").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("number", "note", "match"),
    [("INV-1012", "  ", "note is required"), ("INV-9999", "x", "not in the inbox")],
)
def test_refusals(conn: sqlite3.Connection, offline: Settings, number: str, note: str, match: str):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    with pytest.raises(inbox.InboxError, match=match):
        inbox.resolve(conn, number, approve=True, note=note, reviewer="h")


def test_human_cannot_approve_with_hard_findings(conn: sqlite3.Connection, offline: Settings):
    o = graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    with conn:  # simulate a hard finding on the escalated run (D15 applies to humans too)
        sql = "INSERT INTO findings VALUES (?, ?, ?, ?, 'STOCK_EXCEEDED', 'hard', 'x', '{}')"
        conn.execute(sql, (o.run_id, *o.key))
    with pytest.raises(inbox.InboxError, match="hard findings"):
        inbox.resolve(conn, "INV-1012", approve=True, note="ok", reviewer="h")


def test_resolved_item_cannot_be_resolved_twice(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    inbox.resolve(conn, "INV-1012", approve=False, note="no", reviewer="h")
    with pytest.raises(inbox.InboxError, match="not open"):
        inbox.resolve(conn, "INV-1012", approve=True, note="changed my mind", reviewer="h")


def test_cli_review_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from invoice_agents import cli

    monkeypatch.setattr(cli.console, "width", 250)  # the test runner's 80 columns truncate the table
    dbp = str(tmp_path / "c.db")
    r = CliRunner()
    assert r.invoke(app, ["process", "data/invoices/invoice_1012.txt", "--offline", "--db", dbp]).exit_code == 0
    listing = r.invoke(app, ["review", "--db", dbp])
    assert "INV-1012" in listing.output and "vendor_change" in listing.output
    assert r.invoke(app, ["review", "INV-1012", "--approve", "--db", dbp]).exit_code == 1  # no note
    ok = r.invoke(app, ["review", "INV-1012", "--approve", "--note", "confirmed", "--db", dbp])
    assert ok.exit_code == 0 and "paid" in ok.output
