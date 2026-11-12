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


MAX_PAGES = 10  # invoices are short; more pages is not an invoice, and each page costs a vision call
MAX_PAGE_INCHES = 60  # larger than any paper size an invoice is printed on
MAX_PIXELS = 4_000_000  # per rendered page; bounds memory regardless of the declared page size


def render(data: bytes) -> list[bytes]:
    """PNG bytes of each page, within the page-count, page-size and pixel budgets.

    Raises:
        ValueError: Too many pages, or a page larger than any real document.
    """
    pdf = pdfium.PdfDocument(data)
    if len(pdf) > MAX_PAGES:
        raise ValueError(f"{len(pdf)} pages; scanned invoices are limited to {MAX_PAGES}")
    out: list[bytes] = []
    for i in range(len(pdf)):
        w_pt, h_pt = pdf[i].get_size()
        if max(w_pt, h_pt) > MAX_PAGE_INCHES * 72:
            raise ValueError(f"page {i + 1} is {w_pt / 72:.0f}x{h_pt / 72:.0f} inches")
        scale = RENDER_DPI / 72
        # Shrink oversized pages so width x height stays within the pixel budget.
        scale = min(scale, (MAX_PIXELS / max(w_pt * h_pt, 1)) ** 0.5)
        buf = io.BytesIO()
        pdf[i].render(scale=scale).to_pil().save(buf, format="PNG")  # pyright: ignore[reportArgumentType]
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
