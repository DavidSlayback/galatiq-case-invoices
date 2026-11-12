import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from invoice_agents import graph, roi, telemetry
from invoice_agents.cli import app
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT


def test_cost_uses_published_prices_and_never_guesses():
    u = telemetry.Usage(calls=3, tokens_in=1_000_000, tokens_out=100_000, seconds=12.0)
    assert u.cost("cli:cursor:grok-4.7-medium-fast") == Decimal("2.6000")
    assert u.cost("cli:claude:haiku") == Decimal("0.1500")
    assert u.cost("offline") == Decimal(0)
    assert u.cost("some-unpriced-model") is None  # shown as "unknown", never 0


def test_trace_records_tokens_for_every_agent_call(conn: sqlite3.Connection, offline: Settings):
    o = graph.process_sync(INVOICES / "invoice_1001.txt", offline, conn)  # extract + VP + critic
    lines = [json.loads(x) for x in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    assert {t["node"] for t in lines if "tokens" in t} == {"extract", "vp_propose", "critique"}
    assert telemetry.usage(offline.runs_dir / f"{o.run_id}.jsonl").calls == 3


def test_batch_summary_shows_seconds_and_cost(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from invoice_agents import cli

    monkeypatch.setattr(cli.console, "width", 250)
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    r = CliRunner().invoke(
        app, ["--invoice_dir", "data/invoices/adversarial", "--offline", "--db", str(tmp_path / "b.db")]
    )
    assert r.exit_code == 0 and " $ " in r.output and "0" in r.output


def test_projection_arithmetic():
    a = roi.Assumptions(invoices_per_year=10_000, review_minutes=15, loaded_hourly_cost=60, review_turnaround_days=1)
    p = roi.project(
        a, roi.Measured(escalation_rate=0.2, trap_catch_rate=1.0, cost_per_invoice=0.05, seconds_per_invoice=30)
    )
    assert p.model_cost == pytest.approx(500)
    assert p.review_cost == pytest.approx(2_000 * 0.25 * 60)  # 2,000 reviews x 15 min x $60/h
    assert p.savings == pytest.approx(2_000_000 - 500 - 30_000)
    assert p.cycle_days == pytest.approx(0.8 * 30 / 86_400 + 0.2)


def test_roi_page_recomputes_when_inputs_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INVOICE_DB", str(tmp_path / "ui.db"))
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("INVOICE_MODEL", "offline")
    at = AppTest.from_file(str(ROOT / "app" / "views" / "roi.py"), default_timeout=120)
    at.run()
    assert not at.exception
    before = next(m.value for m in at.metric if m.label == "Annual cost")
    at.number_input[[n.label for n in at.number_input].index("Invoices per year · assumption")].set_value(80_000).run()
    after = next(m.value for m in at.metric if m.label == "Annual cost")
    assert before != after
    assert any("assumption" in n.label for n in at.number_input)  # every assumed input is labelled
