import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from invoice_agents import approval, db, graph, ledger
from invoice_agents.approval import HumanReview
from invoice_agents.cli import app
from invoice_agents.models import Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT

V, N = "Precision Parts Ltd.", "INV-1004"


def run(conn: sqlite3.Connection, s: Settings, name: str):
    return graph.process_sync(INVOICES / name, s, conn)


def test_core_compatibility_tolerates_missing_fields():
    a = {"vendor": "V", "total": "3000.00", "lines": [["WidgetA", "6", "250.00"]], "invoice_date": "2026-01-20"}
    b = {"vendor": "V", "total": "3000.00", "lines": [["WidgetA", "6", "250.00"]], "invoice_date": None}
    assert ledger.conflicts(a, b) == []
    assert ledger.conflicts(a, {**b, "total": "3100.00"}) == ["total"]


def test_two_format_copies_are_skipped(conn: sqlite3.Connection, offline: Settings):
    first = run(conn, offline, "invoice_1011.pdf")
    second = run(conn, offline, "invoice_1011.txt")
    assert (first.status, second.status) == (Status.PAID, Status.DUPLICATE_SKIPPED)
    assert conn.execute("SELECT count(*) FROM payments").fetchone()[0] == 1
    row = db.invoice_row(conn, "Summit Manufacturing Co.", "INV-1011")
    assert row is not None and row["status"] == "paid"  # the skipped copy did not overwrite the original


def test_revision_after_payment_escalates_only_the_delta(conn: sqlite3.Connection, offline: Settings):
    run(conn, offline, "invoice_1004.json")
    r1 = run(conn, offline, "invoice_1004_revised.json")
    assert r1.status == Status.ESCALATED
    sup = [json.loads(e["payload"]) for e in db.events(conn, V, N) if e["event"] == "superseded"]
    assert sup[0]["total_delta"] == "4050.00" and sup[0]["lines_added"] == [["GadgetX", "5", "750.00"]]
    inbox = conn.execute("SELECT reason, amount_due FROM inbox").fetchone()
    assert tuple(inbox) == ("revision_after_payment", "4050.00")
    assert conn.execute("SELECT count(*) FROM payments").fetchone()[0] == 1


def test_revision_while_original_in_inbox_withdraws_and_pays_once(
    conn: sqlite3.Connection, offline: Settings, monkeypatch: pytest.MonkeyPatch
):
    real_route = approval.route

    def hold_original(inv: Any, f: Any, t: Any, due: Any = None) -> Any:
        return HumanReview(inv, f, t, reason="held") if inv.revision == 0 else real_route(inv, f, t, due)

    monkeypatch.setattr(approval, "route", hold_original)
    assert run(conn, offline, "invoice_1004.json").status == Status.ESCALATED
    r1 = run(conn, offline, "invoice_1004_revised.json")
    assert r1.status == Status.PAID and str(r1.amount_paid) == "5940.00"
    assert conn.execute("SELECT status FROM inbox").fetchone()[0] == "withdrawn"
    evts = [e["event"] for e in db.events(conn, V, N)]
    assert "withdrawn" in evts and "superseded" in evts and evts.count("paid") == 1


def test_older_revision_after_newer_is_stale(conn: sqlite3.Connection, offline: Settings):
    run(conn, offline, "invoice_1004_revised.json")
    old = run(conn, offline, "invoice_1004.json")
    assert old.status == Status.DUPLICATE_SKIPPED and "STALE_REVISION" in [f.rule_id for f in old.findings]


def test_same_number_different_content_is_a_fraud_conflict(
    conn: sqlite3.Connection, offline: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    gdir = tmp_path / "golden" / "extract"
    gdir.mkdir(parents=True)
    for src in (ROOT / "fixtures/golden/extract").glob("invoice_1004_json.json"):
        (gdir / src.name).write_text(src.read_text())
    forged = tmp_path / "forged_1004.json"
    forged.write_text('{"invoice_number": "INV-1004", "forged": true}')
    g = json.loads((ROOT / "fixtures/golden/extract/invoice_1004_json.json").read_text())
    g["file_sha256"] = __import__("hashlib").sha256(forged.read_bytes()).hexdigest()
    g["output"]["total"] = "9890.00"
    g["output"]["lines"] = [{"item": "WidgetA", "quantity": "3", "unit_price": "250.00"},
                            {"item": "WidgetB", "quantity": "2", "unit_price": "500.00"},
                            {"item": "WidgetB", "quantity": "8", "unit_price": "1000.00"}]  # fmt: skip
    g["output"]["subtotal"], g["output"]["tax"] = "9750.00", "140.00"
    (gdir / "forged.json").write_text(json.dumps(g))
    replay = offline.with_overrides(golden_dir=tmp_path / "golden")
    run(conn, replay, "invoice_1004.json")
    o = graph.process_sync(forged, replay, conn)
    assert "DUPLICATE_NUMBER_CONFLICT" in [f.rule_id for f in o.findings] and o.status == Status.ESCALATED
    assert "(conflict" in o.key.invoice_number
    row = db.invoice_row(conn, V, N)
    assert row is not None and row["status"] == "paid"  # the original is untouched


def test_batch_and_history_cli(tmp_path: Path):
    dbp = str(tmp_path / "c.db")
    runner = CliRunner()
    r = runner.invoke(app, ["--invoice_dir", "data/invoices", "--offline", "--db", dbp])
    assert r.exit_code == 0 and "duplicate_skipped: 4" in r.output
    h = runner.invoke(app, ["history", "INV-1004", "--db", dbp])
    assert h.exit_code == 0 and "superseded" in h.output and "revision_after_p" in h.output
