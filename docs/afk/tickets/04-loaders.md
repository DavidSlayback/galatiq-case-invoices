# 04 — Format loaders for every sample format

**Source:** [04-loaders.md](../../tickets/04-loaders.md)
**Type:** AFK
**Blocked by:** 03 (needs the RawDocument contract and loader dispatch seam)
**Wave:** 3
**Lane:** loaders
**Verifier profile:** full (untrusted parser)
**What it delivers:** `loaders.load(path)` returns a RawDocument for all 20 sample files (17 logical invoices: 16 numbers plus R1; 3 numbers come in two formats), with deterministic fields where the format allows.

## Context
- Why: FR-1.2. D13 says parsers come first so the LLM confirms rather than guesses.
- Constraining decisions: D13: format loaders feed the LLM extractor; LLM-for-everything was rejected for cost and nondeterminism on clean JSON. PDF uses the pdfplumber text layer; the scan chain is ticket 15. CSV: sniff the key-value layout (header `field,value`, repeated item/quantity/unit_price keys, 1006) vs one row per line with footer total rows (1007, 1015). The 1008 TXT is an email; keep the whole body as text.
- Failure paths: Empty file, binary garbage, an unknown suffix, a malformed XML or CSV → typed LoadError → LOAD_FAILED. Must not execute or evaluate content (untrusted input).
- Plan anchors: PRD FR-1.2; D13

## Acceptance criteria
- [ ] All 20 files in data/invoices load without raising
- [ ] 1006 → 2 lines; 1007 → 3 lines plus subtotal/tax/total; 1015 → 3 lines
- [ ] 1014 XML → currency EUR, 2 lines
- [ ] PDFs 1011/1012/1013 → non-empty text containing the invoice number
- [ ] Malformed inputs (fixtures in tests/fixtures/bad/) → LoadError, never another exception type

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_loaders.py` — 20 sample-file params pass

## Change surface
- invoice_agents/loaders/*.py, tests/test_loaders.py, tests/fixtures/bad/
- Conflict risk: low: owns the loaders package only

## Out of scope
- OCR or vision (ticket 15)
- Field normalisation (ticket 05)

## Completion evidence
- Per-file param test output
