# Execution plan

**Goal:** a reviewer clones the repo, runs one setup command, and watches 17 messy invoices move through extraction, validation, approval and payment. Every outcome matches an expected-outcome scorecard, and every decision can be traced to a rule or an agent's reasoning.

**AFK queue:** [afk/QUEUE.md](afk/QUEUE.md) holds the enriched tickets, waves and human-readiness items.

**Current state (2026-11-12):** the repo holds only the brief (`README.md`), 20 sample files in `data/invoices/` (17 logical invoices), `data/generate_pdfs.py`, and three docs: [PRD.md](PRD.md) (requirements), [DECISIONS.md](DECISIONS.md) (D1–D25, locked by David) and `prd.html` (the page behind the PRD Artifact). There is no code yet.

**Workflow state:**
- Done: intake → grilling → decisions.
- Now: planning. Next: implement ticket 01.
- Resume point: this file plus [tickets/](tickets/). Stop when every ticket's acceptance criteria pass or a human-only blocker remains.

## Scope

**Included:** everything in DECISIONS.md, in the build order of D22: core graph → eval → ledger and inbox → Streamlit → extras → presentation.

**Out of scope:**
- real email or bank integrations, cloud deployment, auth, multi-tenancy, ERP or PO systems (D1 only notes the PO idea);
- partial payment (D4);
- consuming stock (D3);
- live exchange rates (D5).

## Constraints

- No internet at runtime except the configured LLM endpoint. `--offline` runs with no network at all.
- Python, managed with uv. Hard rules live in code, not prompts. Invoice text is untrusted input.
- No GitHub Actions; the local pre-commit and test suite is the gate.
- No API credits. Live models run through the Cursor CLI (Grok) and Claude Code (Max) via a sandboxed bridge (D31, D32).

## Facts checked 2026-11-12

| Fact | Evidence | Consequence |
|---|---|---|
| The whole stack installs on Python 3.14.4 | `uv add` in a scratch project: pydantic-ai-slim 2.68.0, pydantic-graph 2.68.0, anthropic 2.8.0, pdfplumber 0.11.10, pypdfium2 5.15.2, pytesseract 0.3.13, streamlit 1.67.0, rich 15.0.0, typer 0.29.1 | D23 resolves to **Python 3.14**. |
| pydantic-graph 2.x uses a `GraphBuilder` / step / decision API. Loops work, and `graph.render()` emits Mermaid | Spike in the scratchpad: a retry loop ran twice and rendered a `stateDiagram-v2` | The graph and its diagram for the README are confirmed. |
| pydantic-graph 2.x has **no** `persistence` module (the 1.x snapshot persistence is gone) | Import error; the module listing has no persistence file | D11's "persistence for audit" rationale no longer holds. The audit trail is the D25 event ledger, and resuming after a human decision reads our own SQLite state (assumption A3). |
| PydanticAI exports `Agent(output_type=…, retries=…)`, `output_validator`, `ModelRetry`, `FunctionModel`, `TestModel`, `BinaryContent`, `AnthropicModel` | Import and signature introspection | Typed extraction, validator-driven retries, scripted offline models and vision input are all available. |
| No `tesseract` binary on this machine | `command -v tesseract` is empty | The OCR stage (ticket 15) needs David to run `sudo apt install tesseract-ocr`. Until then the chain skips to the vision model. |
| Keys present: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` and others; no `XAI_API_KEY` | `~/user-env.sh` (names only) | The Claude stand-in works now. Live calls use the subscription CLIs (D31). |

## Assumptions (agent choices; change without reopening the design)

- **A1:** the package is `invoice_agents/`, and `main.py` at the repo root is a thin Typer entry point that keeps the brief's `python main.py --invoice_path=…` working.
- **A2:** the model is set by `INVOICE_MODEL` or `--model`; with neither, D32 auto-detect picks one. The live default is `cli:cursor:grok-4.7-medium-fast`, with `cli:claude:haiku` as the cross-check (D31).
- **A3:** a human decision does not resume a paused graph run. It runs a short graph from the stored decision state (approved → pay; rejected → log).
- **A4:** `--offline` replays hand-written golden outputs (`tests/fixtures/golden/`) through a `FunctionModel`, keyed by the input file's sha256. A missing golden fails loudly; it is never guessed. David ruled no live calls unattended (2026-11-12), so live recording and comparison is HITL ticket 19.
- **A5:** rules have stable IDs (for example `STOCK_EXCEEDED`, `PRICE_OVER_CATALOG`) and a severity of `hard`, `soft`, `fraud` or `note`. The agents cite these IDs, and the eval asserts on them.
- **A6:** the mock rate table holds `EUR→USD 1.08` dated 2026-01-31, labelled as mock data.
- **A8:** in the fixed eval order, 1004 is auto-paid before R1 arrives. So per D2, R1's expected outcome is a `superseded` event plus the +$4,050 delta escalated, not a second full payment. `expected_outcomes.yaml` encodes this, which changes PRD §5's draft row.
- **A7:** `mock_payment` keeps the brief's signature and gains an injectable failure hook for FR-4.4. Retry is 2 attempts, then `payment_failed`, which sends the invoice to the inbox.

## Open decisions

None that block the work. None.

## Approach

```
file ─► load (format parser) ─► extract (LLM, typed Invoice) ◄─┐ ≤2 retries on reconcile mismatch
                                      │                         │
                                      ▼                         │
                                 reconcile ─────────────────────┘
                                      ▼
                         ledger check (dup / revision, D2, D25)
                                      ▼
                         validate (rule registry, A5) ─► hard fail ─► reject + log
                                      ▼
                         route tier (D7)
                    ┌─────────────────┼────────────────────┐
              auto-approve     VP agent ⇄ critic (≤2)     human inbox
                    │          approve│reject│disagree──────►│
                    ▼                 ▼                       ▼
                 pay (idempotent) / log rejection ◄── human decision (A3)
```

Every arrow writes an `invoice_events` row and updates the `invoices` status row in one transaction (D25). Agent detail (prompts, tool calls, tokens, latency) goes to `runs/<run_id>.jsonl` (D17).

**Why this shape is the smallest safe one:**
- The LLM only touches extraction (anchored by parsers and arithmetic) and the VP tier (bounded by a code guardrail).
- Everything else is plain functions, testable without a model.
- pydantic-graph supplies the loops and the diagram without a LangChain dependency tree.

## Seams and surfaces

| Surface | Path | Contract |
|---|---|---|
| Domain types | `invoice_agents/models.py` | `RawDocument`, `Invoice`, `LineItem`, `Finding`, `Decision`, `Tier` |
| Storage | `invoice_agents/db.py` | `connect()`, `seed()`, `record(event, state_update)`; append-only trigger |
| Loaders | `invoice_agents/loaders/` | `load(path) -> RawDocument` |
| Agents | `invoice_agents/agents/` | `extractor`, `vp`, `critic`; model from `settings.model` |
| Rules | `invoice_agents/rules.py` | `validate(invoice, db, as_of) -> list[Finding]` |
| Graph | `invoice_agents/graph.py` | `process(path, settings) -> Outcome` |
| Payment | `invoice_agents/payment.py` | `mock_payment(vendor, amount)` |
| CLI | `main.py`, `invoice_agents/cli.py` | `process`, `eval`, `history`, `review`, `reset` |
| UI | `app/streamlit_app.py` | Reads the same DB and calls the same `graph.process` |
| Eval | `eval/expected_outcomes.yaml` | Decision plus the rule IDs that must fire |

## Execution slices

The tickets live in [tickets/](tickets/). Their blocking edges:

```
01 ─► 02 ─► 03 ─┬─► 04 ─► 05 ─┬─► 09 ─► 10 ─► 11 ─► 12
                ├─► 06 ───────┤                      │
                ├─► 07 ───────┤                      ├─► 16
                └─► 08 ───────┘                      │
       09 ─► 13 ─► 14        05 ─► 15                └─► 17 (also needs 13, 14, 15, 16)
       05, 07 ─► 17 (CLI bridge) ─► 18 (live pass, also after 09, 14, 15) ─► 19 (presentation, also after 12–16)
```

**Cut line (D22):** 01–09 is the minimum shippable system. 10–11 complete the ledger and inbox story, 12 is the UI, 13–16 are extras, and 17 is the model bridge, 18 the live pass and 19 the presentation.

## Acceptance evidence ledger

| Outcome | Ticket | Check | Status |
|---|---|---|---|
| End-to-end run from the CLI on one invoice | 03 | `uv run python main.py --invoice_path=data/invoices/invoice_1004.json --offline` exits 0 and shows `paid` | not started |
| All 17 originals match the expected outcomes | 09 | `uv run python main.py eval --offline` passes every non-pending row (all rows after ticket 10) | not started |
| Never pays twice; revisions logged | 10 | Eval batch: 1011/1012/1013 second copies produce `duplicate_skipped`; 1004 R1 produces `superseded` plus an escalated delta | not started |
| Human-in-the-loop path completes | 11 | Test: escalate 1012, `review --approve`, then a `paid` event | not started |
| The LLM can't override hard rules | 07, 14 | Prompt-injection invoice is never `paid` | not started |
| UI usable | 12 | Streamlit smoke test plus a screenshot | not started |
| Live model parity | 18 | `main.py eval` (live) ≥ 16/17; a miss is logged in STATUS | not started |

## Quality gates

- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` passes. Pre-commit runs the same.
- Google-style docstrings on public functions in `models`, `rules`, `graph` and `db`. Comments only for invariants (append-only, guardrail).
- Tests assert on observable behaviour: decisions, events, rule IDs, CLI exit codes. No live network in `pytest`.
- Each ticket names the README or doc section it updates. Cost and latency figures are measured, never estimated.

## Resource plan

- Live LLM spend: a full live eval is roughly 17 invoices × 1–3 extraction calls plus about 5 VP/critic loops. The cap is **$5 per live eval run**; stop and report if a run exceeds it.
- `pytest` and `eval --offline` make no network calls and should finish in under 60 s.
- Single worker; no parallel C++-style builds.

## Completion record

To be filled at the end: changed surfaces, scorecard, docs updated, risks, next action.
