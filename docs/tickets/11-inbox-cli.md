# 11 · Escalation inbox in the CLI

- **Blocked by:** 10
- **Source:** D19, A3
- **Status:** todo

## What
`review --list` shows a table with flags and agent reasoning. `review INV-x --approve|--reject --note TEXT` requires a note, writes a `human_decision` event, and runs the short resume graph (pay or log).

## Surfaces
invoice_agents/inbox.py, invoice_agents/cli.py, tests/test_inbox.py

## Acceptance
- [ ] Escalate 1012 → approve with a note → `paid`
- [ ] A missing `--note` exits non-zero

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: human review

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
