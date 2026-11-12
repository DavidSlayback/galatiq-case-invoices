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
- Constraining decisions: A3: the resume path reads the stored state and runs a short graph (pay or log) rather than resuming a paused run, since pydantic-graph 2.x has no persistence. A note is mandatory. Hard-finding invoices are rejected before routing (D7) and never reach the inbox, and approval with a hard finding is impossible (D15), so there is no override flag. Approving a `revision_after_payment` item pays only the delta (08).
- Failure paths: Unknown invoice → exit 1 with a message. Already resolved → exit 1. A withdrawn (superseded) item → refuse with an explanation.
- Plan anchors: PRD FR-3.4; D19, A3

## Acceptance criteria
- [ ] 1012 (in the inbox by the fixed VP/critic disagreement) → `review INV-1012 --approve --note ok` → `paid`
- [ ] 1004 R1 delta item → approve → one payment of 4,050.00
- [ ] A missing --note exits non-zero
- [ ] `review --list` shows flags, the escalation reason and agent reasoning (the risk score column is added by 13 if present)

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
