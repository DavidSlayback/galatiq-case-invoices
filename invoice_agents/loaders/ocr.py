"""Scanned-PDF support (D16): render pages, try local Tesseract, leave images for a vision model."""

import io
import shutil
from dataclasses import dataclass
from typing import Any, cast

import pypdfium2 as pdfium

MIN_CONFIDENCE = 60.0  # mean word confidence below this means the OCR text is not trusted
RENDER_DPI = 200


@dataclass(frozen=True)
class OcrResult:
    """Rendered page images plus OCR text, if OCR ran and was trusted."""

    images: list[bytes]
    text: str
    note: str


def render(data: bytes) -> list[bytes]:
    """PNG bytes of each page."""
    pdf = pdfium.PdfDocument(data)
    out: list[bytes] = []
    for i in range(len(pdf)):
        buf = io.BytesIO()
        pdf[i].render(scale=RENDER_DPI / 72).to_pil().save(buf, format="PNG")  # pyright: ignore[reportArgumentType]
        out.append(buf.getvalue())
    return out


def tesseract_available() -> bool:
    """Whether the tesseract binary is on PATH (it is an optional system package)."""
    return shutil.which("tesseract") is not None


def ocr(images: list[bytes]) -> tuple[str, float]:
    """Run Tesseract on page images; returns text and mean word confidence (0-100)."""
    import pytesseract
    from PIL import Image

    texts: list[str] = []
    confs: list[float] = []
    for png in images:
        img = Image.open(io.BytesIO(png))
        texts.append(str(pytesseract.image_to_string(img)))
        data = cast(dict[str, list[Any]], pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT))
        confs += [float(c) for c, w in zip(data["conf"], data["text"], strict=False) if w.strip() and float(c) >= 0]
    return "\n\n".join(texts).strip(), (sum(confs) / len(confs) if confs else 0.0)


def scan(data: bytes) -> OcrResult:
    """Render a text-less PDF and OCR it locally when possible; otherwise leave it to the vision model."""
    images = render(data)
    if not tesseract_available():
        return OcrResult(images, "", "ocr skipped: tesseract not installed; vision model will read the page images")
    text, conf = ocr(images)
    if not text or conf < MIN_CONFIDENCE:
        return OcrResult(
            images, "", f"ocr rejected (mean confidence {conf:.0f}); vision model will read the page images"
        )
    return OcrResult(images, text, f"ocr ok (mean confidence {conf:.0f})")
