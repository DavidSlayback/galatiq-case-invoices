# 05 · Extraction agent with normalisation and the self-correction loop

- **Blocked by:** 04
- **Source:** FR-1.1–1.8, D13, D14
- **Status:** todo

## What
The agent produces a typed `Invoice` from a `RawDocument`. The prompt treats document text as untrusted data. SKU canonicalisation (`Widget A`, `WidgetA (rush order)` → `WidgetA`, raw text kept). Date normalisation, with unparseable dates becoming None plus a finding (never a guess). OCR digit repair (`O`→`0`) only inside numeric tokens. An `output_validator` reconciles qty×price, the line sum, subtotal+tax+shipping and the total; on a mismatch it raises `ModelRetry` with the specific numbers, at most 2 retries, after which the result is accepted with an `ARITHMETIC_MISMATCH` finding. Per-field provenance is `parsed`, `llm` or `missing`. Write hand-made golden `Invoice` JSON for all 20 files; the offline model replays them. Live recording is ticket 19.

## Surfaces
invoice_agents/agents/extractor.py, invoice_agents/normalize.py, tests/test_extraction.py, tests/fixtures/golden/*.json

## Acceptance
- [ ] normalize.py unit tests on raw strings; goldens keep stated values and raw OCR tokens (see docs/afk/tickets/05)
- [ ] A scripted model that returns a bad total twice and then a good one: 3 calls, no finding
- [ ] 1009 ends with `ARITHMETIC_MISMATCH` and `NEGATIVE_QUANTITY`, not a 'fixed' total

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: ingestion section

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
