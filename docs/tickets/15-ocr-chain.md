# 15 · Scanned-PDF chain: Tesseract, then vision fallback

- **Blocked by:** 05
- **Source:** D16
- **Status:** todo

## What
If the PDF has no text layer: render with pypdfium2, run Tesseract if the binary exists, and if the result is empty or below the confidence floor, send the page image to the vision model through `BinaryContent`. Add a scanned test invoice made by rasterising 1011.

## Surfaces
invoice_agents/loaders/pdf_loader.py, data/invoices/adversarial/invoice_1011_scan.pdf, tests/test_ocr.py

## Acceptance
- [ ] Offline: the scripted vision model receives an image part for the scanned 1011 (live check is ticket 19)
- [ ] With no tesseract binary, the chain logs a skip and uses vision

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: setup note (optional apt install)

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
