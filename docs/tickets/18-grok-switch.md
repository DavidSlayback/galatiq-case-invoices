# 18 · Switch the default model to Grok

- **Blocked by:** 05, 07
- **Source:** D12 (HITL: David supplies XAI_API_KEY)
- **Status:** todo

## What
Add the xAI provider config. Set `INVOICE_MODEL` to the current Grok model. Re-record fixtures if the outputs differ. Run the live eval.

## Surfaces
invoice_agents/settings.py, .env.example, tests/fixtures/llm/

## Acceptance
- [ ] Live eval on Grok ≥ 16/17
- [ ] The README states Grok as the default

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q && uv run python main.py eval
```

## Docs
README: model section
