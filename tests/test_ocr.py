import io
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from invoice_agents import graph
from invoice_agents.agents import extractor
from invoice_agents.loaders import LoadError, load, ocr
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


def _image_pdf(path: Path, pages: int, px: int = 100, dpi: float = 72) -> Path:
    from PIL import Image

    imgs = [Image.new("RGB", (px, px), "white") for _ in range(pages)]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], resolution=dpi)
    return path


def _decoy_text_pdf(path: Path) -> Path:
    """One page whose only text is an invisible '.', the classic way to dodge an image path."""
    stream = b"BT /F1 1 Tf 3 Tr 10 10 Td (.) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(out)
    return path


def test_too_many_pages_is_refused(tmp_path: Path):
    with pytest.raises(LoadError, match="pages"):
        load(_image_pdf(tmp_path / "many.pdf", ocr.MAX_PAGES + 1))


def test_absurd_page_size_is_refused_before_rendering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    with pytest.raises(LoadError, match="inches"):
        load(_image_pdf(tmp_path / "huge.pdf", 1, px=200, dpi=1))  # 200 x 200 inches


def test_large_page_is_rendered_within_pixel_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from PIL import Image

    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    doc = load(_image_pdf(tmp_path / "big.pdf", 1, px=50, dpi=1))  # 50 x 50 inches
    w, h = Image.open(io.BytesIO(doc.page_images[0])).size
    assert w * h <= ocr.MAX_PIXELS * 1.01


def test_decoy_text_layer_still_takes_the_image_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    doc = load(_decoy_text_pdf(tmp_path / "decoy.pdf"))
    assert doc.page_images and doc.text == ""


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
