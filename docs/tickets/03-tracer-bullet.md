# 03 · Tracer bullet: one JSON invoice end to end

- **Blocked by:** 02
- **Source:** D11, D12, A3, A4
- **Status:** todo

## What
A pydantic-graph `GraphBuilder` graph: load → extract → reconcile → validate → route → pay or reject. JSON loader only. The extractor is a PydanticAI agent whose model comes from settings; offline it replays a recording (A4). Minimal rules: unknown item and stock exceeded. Minimal routing: auto-approve under $10K, otherwise escalate. Events are written at every step. Rich prints a per-invoice panel. `graph.render()` output is saved to `docs/graph.mmd`.

## Surfaces
invoice_agents/{graph,payment,rules}.py, invoice_agents/agents/extractor.py, invoice_agents/loaders/json_loader.py, tests/test_tracer.py, tests/fixtures/llm/

## Acceptance
- [ ] `python main.py --invoice_path=data/invoices/invoice_1004.json --offline` exits 0 with status `paid` and events received→validated→decided→paid
- [ ] 1016 offline gives `rejected` with `UNKNOWN_ITEM`

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q && uv run python main.py reset && uv run python main.py --invoice_path=data/invoices/invoice_1004.json --offline
```

## Docs
README: architecture diagram (generated)

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
