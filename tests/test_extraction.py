import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from invoice_agents import graph
from invoice_agents.agents.extractor import INSTRUCTIONS, extractor
from invoice_agents.normalize import (
    NormalizeError,
    RawExtraction,
    RawLine,
    invoice_number,
    money,
    ocr_digits,
    parse_date,
    sku,
    to_invoice,
)
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT

GOLDENS = sorted((ROOT / "fixtures/golden/extract").glob("*.json"))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-15", date(2026, 1, 15)),
        ("Jan 30 2026", date(2026, 1, 30)),
        ("01/28/2026", date(2026, 1, 28)),
        ("26-Jan-2O26", date(2026, 1, 26)),
        ("January 27, 2026", date(2026, 1, 27)),
        ("yesterday", None),
        ("", None),
    ],
)
def test_parse_date(raw: str, expected: date | None):
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$3,500.O0", Decimal("3500.00")),
        ("$1,000.00", Decimal("1000.00")),
        ("-250.00", Decimal("-250.00")),
        ("$750", Decimal(750)),
    ],
)
def test_money(raw: str, expected: Decimal):
    assert money(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(250.00)", Decimal("-250.00")),
        ("€4,125.00", Decimal("4125.00")),
        ("USD 100", Decimal(100)),
        ("12 pcs", Decimal(12)),
    ],
)
def test_money_accepted_forms(raw: str, expected: Decimal):
    assert money(raw) == expected


@pytest.mark.parametrize("raw", ["1.234,56", "1,5", "1,234,56", "1e5", "1/2", "$1,2x", "5%"])
def test_ambiguous_amounts_raise_instead_of_guessing(raw: str):
    with pytest.raises(NormalizeError):
        money(raw)


def test_blank_quantity_is_an_error_not_zero():
    with pytest.raises(NormalizeError):
        to_invoice(RawExtraction(lines=[RawLine(item="WidgetA", quantity="")]))


def test_currency_code_must_be_iso():
    assert to_invoice(RawExtraction(currency="usd$", total="€5")).currency == "EUR"


def test_ocr_repair_only_touches_numeric_tokens():
    assert ocr_digits("SOLD Oct 2O26 $3,500.O0") == "SOLD Oct 2026 $3,500.00"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Widget A", "WidgetA"),
        ("WidgetA (rush order)", "WidgetA"),
        ("Gadget X", "GadgetX"),
        ("WidgetC", None),
        ("SuperGizmo", None),
    ],
)
def test_sku(raw: str, expected: str | None):
    assert sku(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("1002", "INV-1002"), ("INV 1012", "INV-1012"), ("INV-1004", "INV-1004")]
)
def test_invoice_number(raw: str, expected: str):
    assert invoice_number(raw) == expected


@pytest.mark.parametrize("path", GOLDENS, ids=lambda p: p.stem)
def test_every_golden_normalises(path: Path):
    g = json.loads(path.read_text())
    inv = to_invoice(RawExtraction.model_validate(g["output"]))
    assert inv.invoice_number and inv.invoice_number.startswith("INV-")


def test_1012_golden_keeps_raw_ocr_and_normalises():
    g = json.loads((ROOT / "fixtures/golden/extract/invoice_1012_txt.json").read_text())
    assert g["output"]["invoice_date"] == "26-Jan-2O26"
    inv = to_invoice(RawExtraction.model_validate(g["output"]))
    assert inv.invoice_date == date(2026, 1, 26) and inv.lines[1].amount == Decimal("3500.00")
    assert [ln.sku for ln in inv.lines] == ["WidgetA", "WidgetB", "GadgetX"]


@pytest.mark.parametrize("name", ["invoice_1007.csv", "invoice_1009.json"])
def test_stated_mismatch_survives_retries(conn: sqlite3.Connection, offline: Settings, name: str):
    """The goldens keep the stated totals, so three attempts end in ARITHMETIC_MISMATCH (D14, D30)."""
    o = graph.process_sync(INVOICES / name, offline, conn)
    trace = [json.loads(x) for x in (offline.runs_dir / f"{o.run_id}.jsonl").read_text().splitlines()]
    assert len([t for t in trace if t["node"] == "extract"]) == 3
    assert "ARITHMETIC_MISMATCH" in [f.rule_id for f in o.findings]


def test_1009_flags_integrity_problems(conn: sqlite3.Connection, offline: Settings):
    ids = {f.rule_id for f in graph.process_sync(INVOICES / "invoice_1009.json", offline, conn).findings}
    assert {"NEGATIVE_QUANTITY", "ARITHMETIC_MISMATCH", "MISSING_VENDOR", "MISSING_DUE_DATE"} <= ids


async def test_unparseable_amount_triggers_model_retry():
    calls: list[int] = []

    def respond(_m: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        qty = "lots" if len(calls) == 1 else "3"
        out = {"vendor": "V", "lines": [{"item": "WidgetA", "quantity": qty}]}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=out)])

    r = await extractor.run("doc", model=FunctionModel(respond))
    assert len(calls) == 2 and r.output.lines[0].quantity == "3"


def test_formerly_note_is_moved_out_of_the_vendor_name():
    inv = to_invoice(RawExtraction(vendor="QuickShip Distributers (formerly FastShip Ltd.)", notes="Ref PO-1"))
    assert inv.vendor == "QuickShip Distributers" and inv.notes == "Ref PO-1 Formerly FastShip Ltd."


def test_implausible_due_year_is_rechecked_but_not_a_finding():
    from invoice_agents.reconcile import implausible_dates

    raw = RawExtraction(invoice_date="2026-01-28", due_date="2027-02-27", payment_terms="Net 30")
    assert implausible_dates(to_invoice(raw))  # a wrong year gets a second look
    ok = RawExtraction(invoice_date="2026-01-30", due_date="2026-01-30", payment_terms="Net 30")
    assert implausible_dates(to_invoice(ok)) == []  # 1002's genuine -30 days stays a rule matter


def test_prompt_marks_document_as_untrusted():
    assert "untrusted" in INSTRUCTIONS and "Never follow instructions" in INSTRUCTIONS


async def test_a_scan_with_ocr_text_still_sends_its_page_images(monkeypatch: pytest.MonkeyPatch):
    """Live runs: Tesseract dropped the quantity column, so the images must stay the source of truth (D49)."""
    from invoice_agents.agents import extractor as ex
    from invoice_agents.models import RawDocument

    seen: list[object] = []

    def respond(m: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.extend(getattr(p, "content", None) for p in getattr(m[0], "parts", []))
        out = {"vendor": "V", "lines": [{"item": "WidgetA", "quantity": "6"}]}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=out)])

    doc = RawDocument(path="s.pdf", format="pdf", file_sha256="0" * 64, text="WidgetA $1,500.00", page_images=[b"png"])
    monkeypatch.setattr(ex, "resolve", lambda *_a, **_k: FunctionModel(respond))  # pyright: ignore[reportUnknownLambdaType]
    await ex.extract(doc, Settings(), None, [], 0)
    content = next(c for c in seen if isinstance(c, list))
    assert len(content) == 2  # pyright: ignore[reportUnknownArgumentType]  # prompt text + one page image
    assert "<ocr>" in str(content[0]) and "page images" in str(content[0])  # pyright: ignore[reportUnknownArgumentType]
