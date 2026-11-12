import sqlite3

import pytest

from invoice_agents import graph, vendors
from invoice_agents.models import Finding
from invoice_agents.rules import Reference
from invoice_agents.settings import Settings
from tests.conftest import INVOICES


@pytest.fixture
def reg(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
    ref = Reference.load(conn)
    return {k: str(v["name"]) for k, v in ref.vendors.items()}, ref.aliases


@pytest.mark.parametrize(
    ("name", "kind", "as_"),
    [
        ("Widgets Inc.", "exact", "Widgets Inc."),
        ("widgets  inc.", "exact", "Widgets Inc."),
        ("QuickShip Distributers", "alias", "FastShip Ltd."),
        ("Widgets lnc.", "lookalike", "Widgets Inc."),
        ("\uff37idgets Inc.", "lookalike", "Widgets Inc."),  # full-width W: equal only after folding (B4)
        ("NoProd Industries", "unknown", None),
        ("", "missing", None),
    ],
)
def test_match(reg: tuple[dict[str, str], dict[str, str]], name: str, kind: str, as_: str | None):
    m = vendors.match(name, *reg)
    assert (m.kind, m.registered_as) == (kind, as_)


def risk(o_findings: list[Finding]) -> int:
    return next((int(f.evidence["score"]) for f in o_findings if f.rule_id == "VENDOR_RISK"), 0)


SCORES = [("invoice_1003.txt", 60, 100), ("invoice_1005.json", 60, 100),
          ("invoice_1001.txt", 0, 19), ("invoice_1012.txt", 1, 59)]  # fmt: skip


@pytest.mark.parametrize(("name", "low", "high"), SCORES)
def test_scores_on_samples(conn: sqlite3.Connection, offline: Settings, name: str, low: int, high: int):
    o = graph.process_sync(INVOICES / name, offline, conn)
    assert low <= risk(o.findings) <= high


def test_1012_is_a_rename_not_unknown(conn: sqlite3.Connection, offline: Settings):
    ids = [f.rule_id for f in graph.process_sync(INVOICES / "invoice_1012.txt", offline, conn).findings]
    assert "VENDOR_RENAMED" in ids and "UNKNOWN_VENDOR" not in ids


def test_vp_brief_carries_the_risk_score():
    from invoice_agents.agents.reviewers import case_brief
    from invoice_agents.models import Invoice

    f = Finding(rule_id="VENDOR_RISK", severity="note", message="vendor risk 20/100 (alias)")
    assert "VENDOR_RISK" in case_brief(Invoice(), [f], None) and "20/100" in case_brief(Invoice(), [f], None)
