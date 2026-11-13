"""The agent conversation view: a run's trace told as who said what (thread.py)."""

import json
import sqlite3

from invoice_agents import graph, thread
from invoice_agents.settings import Settings
from tests.conftest import INVOICES


def run_turns(conn: sqlite3.Connection, offline: Settings, name: str) -> list[thread.Turn]:
    o = graph.process_sync(INVOICES / name, offline, conn)
    trace = [json.loads(x) for x in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    return thread.turns(trace)


def test_a_reviewed_invoice_reads_as_a_conversation(conn: sqlite3.Connection, offline: Settings):
    ts = run_turns(conn, offline, "invoice_1010.txt")
    assert [t.speaker for t in ts] == ["extractor", "code", "code", "code", "vp", "critic"]
    assert "propose to **approve**" in ts[4].text and "Cites PRICE_OVER_CATALOG" in ts[4].text
    assert any("Looked up WidgetA in the catalog: 250.00 each, 15 in stock" in d for d in ts[4].details)
    assert any("Looked up the vendor's history: Registered vendor" in d for d in ts[4].details)
    assert ts[5].text == "I agree."


def test_an_auto_paid_invoice_has_no_agent_review(conn: sqlite3.Connection, offline: Settings):
    ts = run_turns(conn, offline, "invoice_1004.json")
    assert {t.speaker for t in ts} == {"extractor", "code"} and "pay it automatically" in ts[-1].text


def test_a_retry_shows_the_mismatch_and_the_second_reading(conn: sqlite3.Connection, offline: Settings):
    ts = run_turns(conn, offline, "invoice_1007.csv")
    retries = [t for t in ts if t.text.startswith("These don't add up")]
    assert retries and retries[0].details and any("(attempt 2)" in t.text for t in ts)


def test_a_failed_extraction_is_said_plainly():
    (t,) = thread.turns([{"node": "extract", "attempt": 0, "error": "Exceeded maximum output retries (2)"}])
    assert t.speaker == "extractor" and "Could not produce a usable reading" in t.text
