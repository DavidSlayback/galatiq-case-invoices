"""Learning from human decisions (D50): a verified vendor-master change stops the next invoice being flagged."""

import json
import sqlite3
from pathlib import Path

import pytest

from invoice_agents import db, graph, inbox
from invoice_agents.models import Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT

FOLLOWUP = ROOT / "data" / "followup" / "invoice_1020.txt"


def flags(o: object) -> set[str]:
    return {f.rule_id for f in o.findings}  # type: ignore[attr-defined]


def test_without_confirmation_the_next_quickship_invoice_is_flagged_again(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    inbox.resolve(conn, "INV-1012", approve=True, note="paid this one", reviewer="human:t")
    nxt = graph.process_sync(FOLLOWUP, offline, conn)
    assert nxt.status == Status.ESCALATED and "VENDOR_RENAMED" in flags(nxt)


def test_a_confirmed_rename_lets_the_next_invoice_through(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    note = "Called FastShip on file number: QuickShip is their new trading name"
    out = inbox.resolve(conn, "INV-1012", approve=True, note=note, reviewer="human:t", update_vendor=True)
    assert out["status"] == "paid"
    row = conn.execute("SELECT confirmed_names_json FROM vendors WHERE name='FastShip Ltd.'").fetchone()
    assert json.loads(row[0]) == ["QuickShip Distributers"]
    events = [e for e in db.events(conn, "FastShip Ltd.", "INV-1012") if e["event"] == "vendor_master_updated"]
    assert len(events) == 1 and json.loads(events[0]["payload"])["note"] == note and events[0]["actor"] == "human:t"
    nxt = graph.process_sync(FOLLOWUP, offline, conn)
    assert nxt.status == Status.PAID and not {"VENDOR_RENAMED", "VENDOR_RISK"} & flags(nxt)


def test_the_vendor_record_changes_only_with_an_approval(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn)
    with pytest.raises(inbox.InboxError, match="only with an approval"):
        inbox.resolve(conn, "INV-1012", approve=False, note="no", reviewer="human:t", update_vendor=True)


def test_an_invoice_with_nothing_to_learn_refuses_the_update(conn: sqlite3.Connection, offline: Settings):
    graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    graph.process_sync(INVOICES / "invoice_1004_revised.json", offline, conn)
    with pytest.raises(inbox.InboxError, match="no vendor-record change"):
        inbox.resolve(conn, "INV-1004", approve=True, note="ok", reviewer="human:t", update_vendor=True)


def test_confirmed_new_bank_details_replace_the_reference_on_file(conn: sqlite3.Connection, offline: Settings):
    o = graph.process_sync(INVOICES / "adversarial" / "invoice_2005_bank_change.txt", offline, conn)
    assert "BANK_DETAILS_CHANGED" in flags(o)
    inbox.resolve(conn, o.key.invoice_number, approve=True, note="verified by callback", reviewer="human:t",
                  update_vendor=True, vendor=o.key.vendor)  # fmt: skip
    remit = next(f.evidence["remit_to"] for f in o.findings if f.rule_id == "BANK_DETAILS_CHANGED")
    row = conn.execute("SELECT bank_ref FROM vendors WHERE name=?", (o.key.vendor,)).fetchone()
    assert row[0] == remit


def test_an_older_database_gains_the_confirmed_names_column(tmp_path: Path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE vendors (name TEXT PRIMARY KEY, address TEXT, known INTEGER NOT NULL,"
                " aliases_json TEXT NOT NULL DEFAULT '[]', bank_ref TEXT)")  # fmt: skip
    old.commit()
    old.close()
    cols = {r[1] for r in db.connect(path).execute("PRAGMA table_info(vendors)")}
    assert "confirmed_names_json" in cols
