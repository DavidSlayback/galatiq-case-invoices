# 11 — Escalation inbox in the CLI

**Source:** [11-inbox-cli.md](../../tickets/11-inbox-cli.md)
**Type:** AFK
**Blocked by:** 10 (resolution must respect ledger state (withdrawn rows, revision deltas))
**Wave:** 7
**Lane:** inbox
**Verifier profile:** self-check
**What it delivers:** `review --list` and `review INV-x --approve|--reject --note TEXT` resolve inbox items, write `human_decision` events, and run the resume path to pay or log.

## Context
- Why: D19; closes the human-in-the-loop path.
- Constraining decisions: A3: the resume path reads the stored state and runs a short graph (pay or log) rather than resuming a paused run, since pydantic-graph 2.x has no persistence. A note is mandatory. Approval of an item with hard findings still requires `--override-hard` plus a note, logged as such (the guardrail applies to humans only with an explicit override).
- Failure paths: Unknown invoice → exit 1 with a message. Already resolved → exit 1. A withdrawn (superseded) item → refuse with an explanation.
- Plan anchors: PRD FR-3.4; D19, A3

## Acceptance criteria
- [ ] Escalate 1012 → `review INV-1012 --approve --note ok` → `paid`
- [ ] A missing --note exits non-zero
- [ ] Approving a hard-finding item without --override-hard fails
- [ ] `review --list` shows flags, risk label and agent reasoning

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_inbox.py` — pass

## Change surface
- invoice_agents/inbox.py, invoice_agents/cli.py, tests/test_inbox.py
- Conflict risk: low

## Out of scope
- The Streamlit inbox (ticket 12)

## Completion evidence
- CLI transcript of the 1012 flow
