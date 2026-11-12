# 03 — Tracer bullet: one JSON invoice end to end through the full graph skeleton

**Source:** [03-tracer-bullet.md](../../tickets/03-tracer-bullet.md)
**Type:** AFK
**Blocked by:** 02 (needs models and the DB)
**Wave:** 2
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** `python main.py --invoice_path=data/invoices/invoice_1004.json --offline` runs every graph stage and pays, with events at each step and a Rich panel; the graph has stub nodes in place for every later stage.

## Context
- Why: Prove the architecture end to end before broadening it, and fix the graph's shape so the wave-3 tickets can fill modules without editing graph.py.
- Constraining decisions: D11: pydantic-graph 2.x `GraphBuilder` with steps, `decision().branch(match(T).to(...))` and `render()` (spiked 2026-11-12; there is no persistence module, so A3 resumes from SQLite). D12 and A4: offline mode replays a hand-written golden extraction through a PydanticAI `FunctionModel` keyed by the input file's sha256 (not the RawDocument text, so loader changes in 04 can't orphan goldens), and a missing golden raises `MissingFixture`. Live recording is ticket 19. Graph nodes: load → extract ⇄ reconcile → ledger_check (pass-through stub) → validate → route → {auto_approve, vp_review (stub → inbox), human_inbox, reject} → pay or log_rejection.
- Failure paths: A missing fixture offline → a clear error naming the file. A non-JSON path at this stage → `LOAD_FAILED` → reject with a logged reason. Never a crash with a traceback.
- Plan anchors: PLAN §Approach diagram; D11, D12, A3, A4

## Acceptance criteria
- [ ] The graph module builds and `graph.render()` is written to docs/graph.mmd
- [ ] 1004 offline gives status `paid` and events received→extracted→validated→decided→paid, in one run_id
- [ ] 1016 offline gives `rejected` with finding UNKNOWN_ITEM
- [ ] Every node writes through `db.record`
- [ ] `runs/<run_id>.jsonl` gets one line per node with timing
- [ ] The approval, payment, ledger and rules modules are called through function seams (`rules.validate`, `approval.route`, `payment.pay`, `ledger.check`), so tickets 06, 07, 08 and 10 don't edit graph.py

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run python main.py reset && uv run python main.py --invoice_path=data/invoices/invoice_1004.json --offline` — exit 0, panel shows PAID
- `uv run python main.py history INV-1004` — not required yet (ticket 10); skip

## Change surface
- invoice_agents/{graph,rules,approval,payment,ledger,trace}.py, invoice_agents/agents/extractor.py, invoice_agents/loaders/{__init__,json_loader}.py, tests/test_tracer.py, tests/fixtures/golden/
- Conflict risk: high: graph.py is the hub; after this ticket only 07 (routing branches) and 10 (ledger branch) may edit it

## Out of scope
- Real rules beyond UNKNOWN_ITEM and STOCK_EXCEEDED
- VP agent
- Formats other than JSON

## Completion evidence
- CLI run transcript
- docs/graph.mmd
