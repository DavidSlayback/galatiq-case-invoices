# 01 · Project scaffold and quality gate

- **Blocked by:** none
- **Source:** agent (D23)
- **Status:** todo

## What
Set up the uv project on Python 3.14 with the `invoice_agents/` package, the Typer CLI in `main.py` (stub subcommands: process, eval, history, review, reset), `settings.py` (model, `--as-of`, db path, `--offline`, runs dir), ruff, pyright (strict), pytest, pre-commit, `.gitignore` (`*.db`, `runs/`), and `.env.example` listing `ANTHROPIC_API_KEY`, `XAI_API_KEY` and `INVOICE_MODEL`.

## Surfaces
pyproject.toml, uv.lock, main.py, invoice_agents/{__init__,settings,cli}.py, tests/test_cli.py, .pre-commit-config.yaml

## Acceptance
- [ ] `uv sync` on a fresh clone succeeds
- [ ] `uv run python main.py --help` lists the subcommands
- [ ] Quality gate passes

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: quickstart stub

> The enriched tickets in [../afk/tickets/](../afk/tickets/) supersede these where they differ.
