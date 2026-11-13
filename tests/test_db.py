import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_agents import db
from invoice_agents.models import EventType, InvoiceKey, Status
from invoice_agents.seed import reset

KEY = InvoiceKey("Widgets Inc.", "INV-1001", 0)


def test_seed_matches_brief(conn: sqlite3.Connection):
    rows = {r["item"]: (r["stock"], r["unit_price"]) for r in conn.execute("SELECT * FROM inventory")}
    assert rows == {
        "WidgetA": (15, "250.00"),
        "WidgetB": (10, "500.00"),
        "GadgetX": (5, "750.00"),
        "FakeItem": (0, "0.00"),
    }
    names = {r["name"] for r in conn.execute("SELECT name FROM vendors")}
    assert "Fraudster LLC" not in names and "FastShip Ltd." in names
    assert conn.execute("SELECT usd_rate FROM fx_rates WHERE currency='EUR'").fetchone()[0] == "1.08"


def test_reset_is_idempotent(tmp_path: Path):
    path = tmp_path / "t.db"
    reset(path).close()
    conn = reset(path)
    assert conn.execute("SELECT count(*) FROM inventory").fetchone()[0] == 4


def test_events_are_append_only(conn: sqlite3.Connection):
    db.record(conn, KEY, EventType.RECEIVED, actor="test", run_id="r1", status=Status.RECEIVED)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE invoice_events SET actor='x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM invoice_events")


def test_record_is_atomic(conn: sqlite3.Connection):
    with pytest.raises(sqlite3.OperationalError):
        db.record(conn, KEY, EventType.RECEIVED, actor="t", run_id="r1", status=Status.RECEIVED, no_such_column=1)
    assert conn.execute("SELECT count(*) FROM invoice_events").fetchone()[0] == 0


def test_record_upserts_status(conn: sqlite3.Connection):
    db.record(conn, KEY, EventType.RECEIVED, actor="t", run_id="r1", status=Status.RECEIVED)
    db.record(conn, KEY, EventType.PAID, actor="t", run_id="r1", status=Status.PAID, total=Decimal("5000.00"))
    row = db.invoice_row(conn, KEY.vendor, KEY.invoice_number)
    assert row is not None and row["status"] == "paid" and row["total"] == "5000.00"
    assert [e["event"] for e in db.events(conn, KEY.vendor, KEY.invoice_number)] == ["received", "paid"]


def test_enqueue_inbox_writes_event_status_and_row(conn: sqlite3.Connection):
    db.enqueue_inbox(conn, KEY, reason="vp_critic_disagree", run_id="r1", actor="approval", label=None)
    row = db.invoice_row(conn, KEY.vendor, KEY.invoice_number)
    assert row is not None and row["status"] == "escalated"
    assert conn.execute("SELECT status FROM inbox").fetchone()[0] == "open"
    assert db.events(conn, KEY.vendor, KEY.invoice_number)[-1]["event"] == "escalated"
