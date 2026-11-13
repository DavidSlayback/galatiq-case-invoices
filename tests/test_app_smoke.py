from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import ROOT

PAGES = ROOT / "app" / "views"


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INVOICE_DB", str(tmp_path / "ui.db"))
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("INVOICE_MODEL", "offline")


def page(name: str) -> AppTest:
    at = AppTest.from_file(str(PAGES / f"{name}.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("name", ["process", "inbox", "history", "batch"])
def test_every_page_renders(name: str):
    page(name)


def test_process_1012_then_approve_in_inbox():
    at = page("process")
    at.selectbox(key="sample").set_value("invoices/invoice_1012.txt").run()
    at.button[0].click().run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "ESCALATED" in body and "INV-1012" in body
    inbox = page("inbox")
    assert "INV-1012" in " ".join(m.value for m in inbox.markdown)
    inbox.text_input[0].set_value("Confirmed the rename with FastShip by phone")
    inbox.button[0].click().run()  # Approve and pay
    assert not inbox.exception
    assert any("paid" in s.value for s in inbox.success)


def test_history_shows_events_after_processing():
    at = page("process")
    at.button[0].click().run()
    hist = page("history")
    assert hist.dataframe and len(hist.dataframe[0].value) >= 4


def test_scorecard_runs_all_pass():
    at = page("batch")
    at.button[0].click().run()
    assert not at.exception
    assert any("ALL PASS" in m.value for m in at.markdown)
