# 04 · Format loaders for every sample format

- **Blocked by:** 03
- **Source:** FR-1.2, D13
- **Status:** todo

## What
Loaders: txt (raw text), csv (detects the key-value vs row-per-line layout), xml, and pdf (pdfplumber text layer). Each returns a `RawDocument` with raw text and any fields it parsed directly. Dispatch by suffix plus sniffing. Unsupported or empty input gives a typed error, which becomes a `LOAD_FAILED` hard finding.

## Surfaces
invoice_agents/loaders/*.py, tests/test_loaders.py

## Acceptance
- [ ] All 22 sample files load without raising
- [ ] 1006 and 1007 CSV layouts give the right line-item counts (2 and 3)
- [ ] 1014 XML parses with currency EUR

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
none
