"""Make an image-only ("scanned") copy of invoice 1011 to exercise the OCR and vision path.

Usage: uv run python scripts/make_scan.py
"""

from pathlib import Path

import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "invoices" / "invoice_1011.pdf"
OUT = ROOT / "data" / "invoices" / "scans" / "invoice_1011_scan.pdf"


def main() -> None:
    """Rasterise each page at 150 dpi and save the images as a PDF with no text layer."""
    pdf = pdfium.PdfDocument(SRC)
    pages = [pdf[i].render(scale=150 / 72).to_pil().convert("RGB") for i in range(len(pdf))]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=150)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
