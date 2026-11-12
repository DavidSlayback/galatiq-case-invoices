import json
import sqlite3
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from invoice_agents import approval, db, graph
from invoice_agents.agents import offline as offline_mod
from invoice_agents.approval import AutoApprove, HumanReview, Reject, VpReview, guard, route
from invoice_agents.models import Decision, Finding, Invoice, Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT


def fnd(sev: str, rid: str = "X") -> Finding:
    return Finding(rule_id=rid, severity=sev, message=rid)  # type: ignore[arg-type]


INV = Invoice(vendor="V", invoice_number="1")


@pytest.mark.parametrize(
    ("total", "findings", "expected"),
    [
        ("9499.99", [], AutoApprove),
        ("9999.99", [], AutoApprove),
        ("10000", [], VpReview),
        ("50000", [], VpReview),
        ("50000.01", [], HumanReview),
        ("100", [fnd("soft")], VpReview),
        ("100", [fnd("note")], AutoApprove),
        ("100", [fnd("fraud")], HumanReview),
        ("100", [fnd("hard"), fnd("fraud")], Reject),
        ("60000", [fnd("hard")], Reject),
        (None, [], HumanReview),
    ],
)
def test_route_tiers(total: str | None, findings: list[Finding], expected: type):
    r = route(INV, findings, Decimal(total) if total else None)
    assert type(r) is expected


def test_fraud_route_is_labelled():
    r = route(INV, [fnd("fraud", "SUSPICIOUS_ADDRESS")], Decimal(100))
    assert isinstance(r, HumanReview) and r.label == approval.FRAUD_LABEL


def test_guard_blocks_approval_with_hard_findings():
    d, overridden = guard(Decision(kind="approve", actor="vp_agent"), [fnd("hard", "STOCK_EXCEEDED")])
    assert overridden and d.kind == "reject" and d.actor == "guardrail" and d.cited_rule_ids == ["STOCK_EXCEEDED"]
    assert guard(Decision(kind="approve", actor="vp_agent"), [fnd("soft")]) == (
        Decision(kind="approve", actor="vp_agent"),
        False,
    )


# --- the loop, end to end, with scripted reviewers -------------------------

LINES = [
    {"item_raw": "WidgetA", "sku": "WidgetA", "quantity": "15", "unit_price": "250.00"},
    {"item_raw": "WidgetB", "sku": "WidgetB", "quantity": "10", "unit_price": "500.00"},
    {"item_raw": "GadgetX", "sku": "GadgetX", "quantity": "5", "unit_price": "750.00"},
]
SRC = INVOICES / "invoice_1004.json"


def approve(*ids: str) -> dict[str, Any]:
    return {"decision": "approve", "reasons": ["ok"], "cited_rule_ids": list(ids)}


@pytest.fixture
def goldens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Point offline replay at a temp dir; returns a writer for vp/critic scripts."""
    base = json.loads((ROOT / "fixtures/golden/extract/invoice_1004.json").read_text())
    base["output"] |= {"lines": LINES, "subtotal": "12500.00", "tax": "0", "total": "12500.00"}
    gdir = tmp_path / "golden"
    for kind in ("extract", "vp", "critic"):
        (gdir / kind).mkdir(parents=True)
    (gdir / "extract" / "g.json").write_text(json.dumps(base))

    def script(kind: str, attempts: list[dict[str, Any]]) -> None:
        g = {"source": "x", "file_sha256": base["file_sha256"], "attempts": attempts}
        (gdir / kind / "g.json").write_text(json.dumps(g))

    monkeypatch.setattr(offline_mod, "GOLDEN_DIR", gdir)
    offline_mod._index.cache_clear()  # pyright: ignore[reportPrivateUsage]
    yield script
    offline_mod._index.cache_clear()  # pyright: ignore[reportPrivateUsage]


def run(conn: sqlite3.Connection, offline: Settings) -> tuple[Any, list[dict[str, Any]]]:
    o = graph.process_sync(SRC, offline, conn)
    trace = [json.loads(x) for x in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    return o, trace


def test_vp_approves_and_critic_agrees(conn: sqlite3.Connection, offline: Settings, goldens: Any):
    goldens("vp", [approve()])
    goldens("critic", [{"agrees": True}])
    o, _ = run(conn, offline)
    assert o.status == Status.PAID and o.decision is not None and o.decision.actor == "vp_agent"


def test_disagreement_for_two_rounds_goes_to_inbox(conn: sqlite3.Connection, offline: Settings, goldens: Any):
    goldens("vp", [approve(), approve()])
    goldens("critic", [{"agrees": False, "objections": ["a"]}, {"agrees": False, "objections": ["b"]}])
    o, trace = run(conn, offline)
    assert o.status == Status.ESCALATED
    assert [t["round"] for t in trace if t["node"] == "critique"] == [0, 1]
    assert conn.execute("SELECT reason FROM inbox").fetchone()[0] == "vp_critic_disagree"


def test_invented_citation_is_objected_in_code(conn: sqlite3.Connection, offline: Settings, goldens: Any):
    goldens("vp", [approve("MADE_UP"), approve()])
    goldens("critic", [{"agrees": True}])
    o, trace = run(conn, offline)
    crit = [t for t in trace if t["node"] == "critique"]
    assert "MADE_UP" in crit[0]["verdict"]["objections"][0] and o.status == Status.PAID


def test_guardrail_overrides_reviewers(
    conn: sqlite3.Connection, offline: Settings, goldens: Any, monkeypatch: pytest.MonkeyPatch
):
    """Even if a hard finding reached review, an agreed approval becomes a rejection."""
    goldens("vp", [approve()])
    goldens("critic", [{"agrees": True}])
    hard = fnd("hard", "STOCK_EXCEEDED")
    monkeypatch.setattr(approval, "route", lambda inv, f, t: VpReview(inv, [*f, hard], t))  # pyright: ignore
    o, _ = run(conn, offline)
    assert o.status == Status.REJECTED and o.decision is not None and o.decision.actor == "guardrail"
    assert "guardrail_override" in [e["event"] for e in db.events(conn, "Precision Parts Ltd.", "INV-1004")]
