"""The review agents' tools (D48): read-only lookups, carried by every backend, and bounded."""

import json
import sqlite3
from decimal import Decimal

import pytest
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from invoice_agents import db, graph, lookups
from invoice_agents.agents import cli_bridge, reviewers
from invoice_agents.models import EventType, InvoiceKey, RawDocument, Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES

KEY = InvoiceKey("Widgets Inc.", "INV-500", 0)


def paid_invoice(conn: sqlite3.Connection, number: str, amount: str) -> None:
    key = InvoiceKey("Widgets Inc.", number, 0)
    db.record(
        conn, key, EventType.RECEIVED, actor="t", run_id="r", status=Status.RECEIVED, total=amount, currency="USD"
    )
    attempt = db.start_payment(conn, key, Decimal(amount), "USD", Decimal(amount))
    assert attempt is not None
    db.settle_payment(conn, key, attempt, run_id="r", actor="t", payload={"amount": Decimal(amount)})


def test_vendor_history_summarises_other_invoices_only(conn: sqlite3.Connection):
    paid_invoice(conn, "INV-1", "100.00")
    paid_invoice(conn, "INV-2", "250.00")
    paid_invoice(conn, KEY.invoice_number, "999.00")  # the invoice under review is left out
    h = lookups.vendor_history(conn, KEY)
    assert h["invoices_on_file"] == {"paid": 2} and h["total_paid"] == {"USD": "350.00"}
    assert {r["invoice_number"] for r in h["recent"]} == {"INV-1", "INV-2"}


def test_vendor_history_of_a_new_vendor_is_empty(conn: sqlite3.Connection):
    h = lookups.vendor_history(conn, InvoiceKey("Nobody Ltd.", "INV-1", 0))
    assert h["invoices_on_file"] == {} and h["recent"] == [] and h["open_review_items"] == 0
    assert h["in_registry"] is False and h["note"].startswith("NOT in the vendor registry")


def test_a_registered_vendor_with_no_history_says_so(conn: sqlite3.Connection):
    """A live critic read an empty history as an unconfirmed payee; the tool now states registry status."""
    h = lookups.vendor_history(conn, KEY)
    assert h["in_registry"] is True and "normal for a first invoice" in h["note"]


def test_catalog_item(conn: sqlite3.Connection):
    assert lookups.catalog_item(conn, "WidgetA") == {"sku": "WidgetA", "in_catalog": True, "stock": 15,
                                                      "unit_price": "250.00"}  # fmt: skip
    assert lookups.catalog_item(conn, "WidgetZ") == {"sku": "WidgetZ", "in_catalog": False}


def test_offline_review_runs_the_tools_and_traces_them(conn: sqlite3.Connection, offline: Settings):
    o = graph.process_sync(INVOICES / "invoice_1010.txt", offline, conn)
    trace = [json.loads(x) for x in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    vp = next(t for t in trace if t["node"] == "vp_propose")
    assert [c["tool"] for c in vp["tools"]] == ["vendor_history", "catalog_item"] and o.status == Status.PAID


async def test_cli_bridge_carries_a_tool_call_and_its_result(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    replies = [
        {"tool_call": {"name": "catalog_item", "arguments": {"sku": "WidgetA"}}},
        {"answer": {"decision": "approve", "reasons": ["at catalog"], "cited_rule_ids": []}},
    ]
    prompts: list[str] = []

    async def fake_run(argv: list[str], cwd: str, timeout_s: int, prompt: str) -> tuple[str, str, int, float]:
        prompts.append(prompt)
        return json.dumps({"structured_output": replies[len(prompts) - 1]}), "", 0, 0.1

    monkeypatch.setattr(cli_bridge, "_run", fake_run)
    model = cli_bridge.CliBackend(tool="claude", model="haiku").as_model()
    r = await reviewers.vp_agent.run("brief", model=model, deps=reviewers.ReviewContext(conn, KEY))
    assert r.output.decision == "approve" and "# Tools" in prompts[0] and "catalog_item" in prompts[0]
    assert "# Result of catalog_item" in prompts[1] and '"unit_price":"250.00"' in prompts[1]


async def test_a_model_stuck_calling_tools_is_stopped(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch):
    def loop(_m: list[ModelMessage], _i: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name="vendor_history", args={})])

    monkeypatch.setattr(reviewers, "resolve", lambda *_a, **_k: FunctionModel(loop))  # pyright: ignore[reportUnknownLambdaType]
    doc = RawDocument(path="x", format="txt", file_sha256="0" * 64, text="x")
    with pytest.raises(AgentRunError):
        await reviewers.propose(doc, Settings(), reviewers.ReviewContext(conn, KEY), "brief", [], [], 0)
