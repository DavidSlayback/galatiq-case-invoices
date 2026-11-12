import json
import sqlite3

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from invoice_agents import graph
from invoice_agents.agents import extractor
from invoice_agents.loaders import load, ocr
from invoice_agents.models import Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT

SCAN = INVOICES / "scans" / "invoice_1011_scan.pdf"


def test_scan_has_no_text_layer_but_loads_as_images(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    doc = load(SCAN)
    assert doc.text == "" and len(doc.page_images) == 1 and doc.page_images[0][:4] == b"\x89PNG"
    assert "tesseract not installed" in doc.fields["ocr"]


def test_low_confidence_ocr_falls_back_to_vision(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: True)
    monkeypatch.setattr(ocr, "ocr", lambda images: ("garbage", 12.0))  # pyright: ignore[reportUnknownLambdaType]
    doc = load(SCAN)
    assert doc.text == "" and "rejected" in doc.fields["ocr"]


def test_trusted_ocr_text_is_used(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: True)
    monkeypatch.setattr(ocr, "ocr", lambda images: ("INVOICE INV-1011 Total $3,000.00", 91.0))  # pyright: ignore[reportUnknownLambdaType]
    assert "INV-1011" in load(SCAN).text


@pytest.mark.skipif(not ocr.tesseract_available(), reason="tesseract binary not installed (optional, H2)")
def test_real_tesseract_reads_the_scan():
    assert "1011" in load(SCAN).text


async def test_vision_model_receives_page_image(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    doc = load(SCAN)
    seen: list[object] = []
    golden = json.loads((ROOT / "fixtures/golden/extract/invoice_1011_scan_pdf.json").read_text())["output"]

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        req = messages[-1]
        assert isinstance(req, ModelRequest)
        for part in req.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                seen.extend(part.content)
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=golden)])

    monkeypatch.setattr(extractor, "resolve", lambda *a, **k: FunctionModel(respond))  # pyright: ignore
    out = await extractor.extract(doc, Settings(model="x"), None, [], 0)
    assert any(isinstance(c, BinaryContent) and c.media_type == "image/png" for c in seen)
    assert out.invoice.invoice_number == "INV-1011"


def test_scan_runs_end_to_end_offline(conn: sqlite3.Connection, offline: Settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    o = graph.process_sync(SCAN, offline, conn)
    assert o.status == Status.PAID and o.invoice is not None and str(o.invoice.total) == "3000.00"
