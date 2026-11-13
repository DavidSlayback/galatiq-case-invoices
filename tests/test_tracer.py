import json
import sqlite3
from pathlib import Path

import pytest

from invoice_agents import db, graph
from invoice_agents.agents.offline import MissingFixture
from invoice_agents.models import Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT


def test_1004_is_paid_end_to_end(conn: sqlite3.Connection, offline: Settings):
    o = graph.process_sync(INVOICES / "invoice_1004.json", offline, conn)
    assert o.status == Status.PAID and o.amount_paid is not None and str(o.amount_paid) == "1890.00"
    evts = [e["event"] for e in db.events(conn, "Precision Parts Ltd.", "INV-1004")]
    assert evts == ["received", "extracted", "validated", "decided", "paid"]
    assert {e["run_id"] for e in db.events(conn, "Precision Parts Ltd.", "INV-1004")} == {o.run_id}
    trace = [json.loads(line)["node"] for line in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    assert trace[:3] == ["load", "extract", "reconcile"]


def test_1016_rejected_for_unknown_item(conn: sqlite3.Connection, offline: Settings):
    o = graph.process_sync(INVOICES / "invoice_1016.json", offline, conn)
    assert o.status == Status.REJECTED
    assert [f.rule_id for f in o.findings] == ["UNKNOWN_ITEM"]


def test_unreadable_file_is_rejected_not_crashed(conn: sqlite3.Connection, offline: Settings, tmp_path: Path):
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    o = graph.process_sync(bad, offline, conn)
    assert o.status == Status.REJECTED and o.findings[0].rule_id == "LOAD_FAILED"


def test_missing_golden_is_an_error(conn: sqlite3.Connection, offline: Settings, tmp_path: Path):
    f = tmp_path / "new.json"
    f.write_text('{"invoice_number": "X"}')
    with pytest.raises(MissingFixture):
        graph.process_sync(f, offline, conn)


def test_reconcile_retries_then_accepts(
    conn: sqlite3.Connection, offline: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A wrong total twice, then a right one: three extractor calls, no finding."""
    golden = json.loads((ROOT / "fixtures/golden/extract/invoice_1004_json.json").read_text())
    bad = {**golden["output"], "total": "9999.00"}
    golden["attempts"] = [bad, bad, golden["output"]]
    (tmp_path / "extract").mkdir()
    (tmp_path / "extract" / "g.json").write_text(json.dumps(golden))
    o = graph.process_sync(INVOICES / "invoice_1004.json", offline.with_overrides(golden_dir=tmp_path), conn)
    attempts = [json.loads(x) for x in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    assert [a["attempt"] for a in attempts if a["node"] == "extract"] == [0, 1, 2]
    assert o.status == Status.PAID and o.findings == []


def test_graph_diagram_is_current():
    assert (ROOT / "docs" / "graph.mmd").read_text() == graph.mermaid() + "\n"
