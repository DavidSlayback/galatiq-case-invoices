# 01 — Project scaffold and quality gate

**Source:** [01-scaffold.md](../../tickets/01-scaffold.md)
**Type:** AFK
**Blocked by:** None
**Wave:** 0
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** A uv project on Python 3.14 with an importable `invoice_agents` package, a Typer CLI and a passing local quality gate.

## Context
- Why: Every later ticket needs a runnable package, settings and a gate; nothing else can start.
- Constraining decisions: D23: uv, ruff, pyright strict, pytest, pre-commit, Python 3.14 (verified to install on 2026-11-12); pip/requirements was rejected for lacking a lockfile. A1: `main.py` stays a thin entry point so the brief's `python main.py --invoice_path=` works. A2: the default model is `anthropic:claude-haiku-5-5` (David, 2026-11-12). No GitHub Actions: the local gate is the CI.
- Failure paths: Missing API key → settings load fine, and only a live model call errors with a clear message. Unknown subcommand → Typer exits 2.
- Plan anchors: PLAN §Constraints, §Quality gates; D23

## Acceptance criteria
- [ ] `uv sync` on a fresh clone succeeds on Python 3.14
- [ ] `uv run python main.py --help` lists process, eval, history, review, reset, ui
- [ ] `uv run python main.py --invoice_path=X` is accepted (an alias of `process X`)
- [ ] `settings.py` reads INVOICE_MODEL (default `anthropic:claude-haiku-5-5`), INVOICE_DB, `--as-of` (default 2026-02-01), `--offline`, RUNS_DIR
- [ ] `.env.example` lists ANTHROPIC_API_KEY, XAI_API_KEY, INVOICE_MODEL; `.gitignore` covers `*.db`, `runs/`, `.env`
- [ ] pre-commit runs ruff, ruff-format, pyright and pytest

## Verification
- `uv sync && uv run python main.py --help` — exit 0, the 6 subcommands listed
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uvx pre-commit run --all-files` — all hooks pass

## Change surface
- pyproject.toml, uv.lock, main.py, invoice_agents/{__init__,settings,cli}.py, tests/test_cli.py, .pre-commit-config.yaml, .gitignore, .env.example
- Conflict risk: low: greenfield

## Out of scope
- Any domain logic
- Writing the README beyond the quickstart stub

## Completion evidence
- Gate output
- `--help` output in the PR body
