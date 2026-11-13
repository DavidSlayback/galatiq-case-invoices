# Decision log

Decisions from the grilling session on 2026-11-12. Each one comes from David unless it is marked otherwise. Requirement IDs refer to [PRD.md](PRD.md); B-ids are the brainstorm questions in PRD §6.

## Domain rules

| # | Decision | Why / consequence |
|---|---|---|
| D1 (B-1) | Check stock literally: quantity ≤ stock. The README adds one sentence: "read as a goods-received check; production would do a PO / receipt three-way match." | Matches the brief's expected outcomes. The invoices are bills to Acme ("Bill To: Acme", "Attn: Accounts Payable"), so Acme is the buyer. |
| D2 (B-2) | Keep a ledger keyed by vendor + invoice number (revision is a column, not part of the key). A copy with the same content is skipped as a duplicate. A higher revision replaces the original if it is unpaid; if the original was paid, pay only the difference or escalate. Every replacement and every skipped duplicate is written to the event ledger (D25). | Never pay twice (1011–1013 come in two formats; 1004 has a revision R1). |
| D3 (B-3) | Do not consume stock. Every invoice is checked against the seeded stock. | Outcomes don't depend on batch order. The README notes that production would reserve stock. |
| D4 (B-4) | No partial approval. Reject the whole invoice; the rejection notice lists the bad lines. | Accounts payable doesn't short-pay without a credit note (1016). |
| D5 (B-5) | Convert currency with a fixed, dated mock rate table, then apply the normal rules. Foreign currency is a note, not a flag. | 1014 is in EUR. Works offline. |
| D6 (B-6) | Add a `unit_price` column. A price more than 5% above catalog is a soft flag; discounts are noted only. | 1010's rush line escalates; 1013's discounts pass. |
| D7 (B-7) | Hard failures (unknown item, stock overrun, arithmetic or integrity errors) reject before approval. Under $10K with no flags: auto-approve. $10K–$50K, or any soft flag: VP agent review. Over $50K, or any fraud signal: human. A total of $9.5K–$10K is a soft flag. | Keeps the LLM on the cases that need judgement. |
| D8 | The processing date comes from `--as-of`, default 2026-02-01. | The data is dated Jan–Feb 2026; against the real date, every invoice would be past due. |
| D9 | Seed the vendor registry with the plausible vendors. Unknown vendors: Fraudster LLC, NoProd Industries, Global Supply Chain Partners, and the blank vendor. QuickShip matches FastShip Ltd. only through an alias, which raises a "vendor renamed" soft flag. | Makes the unknown-vendor and renamed-vendor paths real. |
| D10 | Fraud signals (unknown vendor plus urgency or wire language, a lookalike name, changed bank details, prompt injection) always escalate to a human with a "suspected fraud" label. They never auto-reject. Hard failures still reject first. | Avoids false-positive rejections of real vendors. |

## Architecture

| # | Decision | Why / consequence |
|---|---|---|
| D11 (B-8) | Agents use PydanticAI; the workflow graph uses pydantic-graph. | Typed structured outputs and tools, a Mermaid diagram for free, and persistence for the audit trail. One dependency family. |
| D12 (B-12) | The model is set in config. *Amended by D31 and D32:* live runs use Grok via the Cursor CLI, with Claude via Claude Code as a cross-check; there are no API credits. A scripted PydanticAI `FunctionModel` runs tests and the `--offline` demo. | The brief prefers Grok, and there is no key yet. Tests need no network. |
| D13 (B-10) | Format loaders (json, csv, xml, pdf text) run first. The LLM extraction agent always produces the typed `Invoice`, and deterministic checks reconcile the totals. | Agentic, yet anchored by the parsers. |
| D14 (B-11) | Extraction self-correction: feed the specific mismatch back, at most 2 retries, then keep the result with an "arithmetic mismatch" finding, which validation rejects. | The LLM must not invent consistency (1009's mismatch is real). |
| D15 (B-9, B-11) | In the VP tier, a VP agent proposes approve or reject, citing rule IDs. A separate critic agent checks it. If they still disagree after 2 rounds, a human decides. A code guardrail makes approval impossible when any hard rule failed. | The LLM has real but bounded authority (FR-3.6). |
| D16 (B-13) | PDFs: use the text layer if present. Otherwise run Tesseract OCR, and if OCR is empty or low-confidence, fall back to a vision model. | David answered "3 then 1": local first, model last. |
| D17 | Business data (inventory with prices, vendors, ledger, findings, decisions, payments, inbox) lives in SQLite. The business-level history is the event ledger (D25); the JSONL traces are agent-level detail. Per-run agent traces (prompts, tool calls, tokens, latency) go to JSONL under `runs/`. | Large trace data stays out of the database. |

## Product

| # | Decision | Why / consequence |
|---|---|---|
| D18 (B-14) | A Rich CLI (a panel per invoice and a batch summary) plus a Streamlit dashboard (submit an invoice, follow the stages, inbox, trace view, ROI). | Pure Python. Addresses the UI/UX criterion. |
| D19 | Escalation inbox in both the CLI (`main.py review` / `review INV-x --approve --note ...`) and Streamlit. A human decision requires a note and finishes through the same settlement step that ends a graph run (D42); no graph run is paused. | Closes the human-in-the-loop path. |
| D20 (B-15) | Extras in scope: an eval harness (`expected_outcomes.yaml` plus `main.py eval`); adversarial invoices (prompt injection, split invoices just under the threshold, a lookalike vendor, an image-only scan, a bank-detail change); a vendor registry with a risk score; a cost, latency and ROI panel. | All four were selected. |
| D21 (B-16) | The ROI panel takes editable assumptions (invoices per year, 30% error rate, 5-day delay, $2M) and labels any assumed volume. Savings come from measured cost, latency and catch rate. | The brief gives no invoice volume, so we don't invent one. |
| D22 (B-17) | Build order: (1) core graph, CLI and seeded database; (2) eval on the 17 original invoices; (3) ledger and inbox; (4) Streamlit; (5) vendor risk, adversarial files, OCR chain, ROI. If time runs short, cut from the end. | Correctness is proven early. |
| D23 | Tooling: uv, ruff, pyright and pytest, with pre-commit as the local gate. Use the highest Python version every dependency supports: try 3.14 first and step down only if a wheel is missing. | David asked for the newest Python. |
| D24 | Presentation: a README (quickstart, generated Mermaid graph, this decision log, eval scorecard, ROI, limitations), a demo video, and a Claude Artifact in place of a slide deck. | The graders score presentation and business impact. |

## Added 2026-11-12 (after the grilling)

| # | Decision | Why / consequence |
|---|---|---|
| D25 | An append-only `invoice_events` table in SQLite is the audit history. It records `received`, `duplicate_skipped`, `superseded`, `validated`, `decided`, `escalated`, `human_decision`, `paid` and `payment_failed`. Each event carries the invoice key, revision, actor (agent, rule or human), a timestamp, the trace id and a JSON payload. A `superseded` event names the old and new revision and gives the line and amount differences and the reason. Each step appends its event and updates a current-status row in the same transaction. A trigger blocks UPDATE and DELETE on events. `main.py history INV-x` and the Streamlit trace view read the events. | David: replacements must be logged and referable. A state table alongside the events keeps the inbox and other queries simple. |

## Added after the AFK queue review (2026-11-12, agent choices; flag if wrong)

| # | Decision | Why / consequence |
|---|---|---|
| D25a | The event-type list is extended: `extracted`, `guardrail_override`, `withdrawn`, `payment_skipped_already_paid`, `revision_after_payment`. | The tickets needed these. |
| D26 | DUE_TERMS_MISMATCH tolerates ±1 day. | Vendors count terms inclusively. Without the tolerance, almost every invoice is a soft flag and nothing auto-approves. |
| D27 | Boundaries: NEAR_THRESHOLD is 9,500 ≤ total < 10,000. VP is 10,000 ≤ total ≤ 50,000; human is > 50,000. PAST_DUE is due < as_of. DUE_BEFORE_INVOICE is due ≤ invoice date. UNKNOWN_VENDOR alone is soft; with urgency or wire language it becomes the fraud rule UNKNOWN_VENDOR_PRESSURE (D10 as written). | Removes ambiguity at the edges. |
| D28 | Fixed VP-tier outcomes for the eval: 1001 approve, 1010 approve, 1012 VP approve then critic objects twice → inbox. | Stops the eval from being circular; gives the inbox a natural sample. |
| D29 | Payments go out in the invoice currency (1014: EUR 4,125.00) with the USD equivalent recorded (4,455.00); tiers and price rules use USD. | The mock_payment signature has no currency field. |
| D30 | Two invoices state a wrong total, and both expected outcomes require ARITHMETIC_MISMATCH. INV-1007: 14,750 + 885 = 15,635, not 15,525. INV-1013: 21,040.00 + 1,472.80 = 22,512.80, not 22,562.80 ($50 over). | The PRD missed both. A fresh-context review found 1007; the reconcile step found 1013 on its first run. |

## Model backends (David, 2026-11-12)

| # | Decision | Why / consequence |
|---|---|---|
| D31 | No API credits are bought. Live calls go through David's subscriptions: Grok 4.7 via `cursor-agent -p` (Cursor Pro) is the default, and Claude Haiku via `claude -p` (Claude Max) is the cross-check. Both are wrapped as a PydanticAI `FunctionModel` bridge, sandboxed in an empty temp dir with tools off or read-only. Unattended live runs are allowed (about 100–200 calls). | Uses the plans David already pays for and honours "use Grok". Invoices are untrusted, so the agent CLIs must not have tools that act. |
| D32 | When no model is configured, pick one automatically: `XAI_API_KEY` → xAI API; another API key → that API; a logged-in `cursor-agent` or `claude` → the CLI bridge; otherwise `--offline` replay with a banner. | Graders without David's logins can always run it. |

## After the live pass (2026-11-12, agent choices; flag if wrong)

| # | Decision | Why / consequence |
|---|---|---|
| D33 | Vendor-master changes (`VENDOR_RENAMED`) go straight to a human, labelled "vendor change". This replaces D28's scripted VP/critic deadlock for 1012. | On the live pass both Grok and Haiku approved 1012, because the registry links QuickShip to FastShip. The decision belongs to a person confirming the change, not to model judgement. AP practice is to verify vendor-master changes out of band. |
| D34 | The extractor's reconcile step also re-checks due dates more than 45 days off the stated terms (a likely wrong year). This never becomes a finding by itself. | Haiku misread 2026 as 2027 on the control invoice. |
| D35 | A "(formerly X)" note is moved out of the vendor name into notes. | Haiku kept it in the name, which changed the ledger key and broke duplicate detection on 1012. |

## Final review fixes (2026-11-12, agent choices; flag if wrong)

| # | Decision | Why / consequence |
|---|---|---|
| D36 | Ledger keys are NFKC- and whitespace-normalised, and vendor and number compare case-insensitively in every table. | Otherwise "WIDGETS INC." could be paid again (review B1). |
| D37 | A unit price is derived from the line amount when only an amount is stated; a line with no price at all raises PRICE_UNVERIFIABLE (soft). A total ≤ 0 or a negative unit price is hard. A payment ≤ 0 is recorded as a credit due, never sent to the bank. | Review B2 and B6. |
| D38 | A vendor name that matches the registry only after Unicode folding is a look-alike. One normaliser is used for every vendor comparison. | A full-width "Widgets" passed as exact and skipped the bank check (B4). |
| D39 | The injection rule scans the raw document text and every extracted string. Inbox actions resolve by inbox id or vendor and refuse ambiguity. A conflicting copy counts what the original was paid. CLI prompts go on stdin. | Review B3, B5, B7, B8. |
| D40 | Invoice identity lives in one module (`identity.py`). One fold (NFKC, Unicode casefold, single spaces) is used in Python and, as the SQLite collation `FOLD`, on every key column. An exact or alias vendor name is keyed under its registered name; a look-alike is not. Conflict copies are matched by number, not `LIKE`. Typed invoice numbers are normalised. | `NOCASE` folds only ASCII, so "Müller GmbH" and "MÜLLER GMBH" could both be paid, and an alias resubmission escaped the duplicate check. Agent choice from the architecture review (docs/REFACTOR.md). |
| D41 | The store (`db.py`) exposes business transitions, not tables. Each of these is one transaction: start, settle or fail a payment; record findings; withdraw inbox items; resolve an inbox item. A payment writes a `pending` row before the bank call and settles it afterwards. A pending row found later is never re-sent; it goes to the inbox as `payment_unconfirmed`. Approve means the reviewer saw the payment at the bank; reject clears it and queues a `payment_failed` retry. | A crash between the bank call and the ledger write could pay twice, and the PAYMENT_FAILED event and its inbox row, like the human decision and the inbox close, were separate commits. This makes D25's "same transaction" true. Agent choice (docs/REFACTOR.md). |
| D42 | Settlement is one module (`settle.py`). It applies the guardrail, writes DECIDED, then pays or writes REJECTED with the bad lines. The graph's final step and `inbox.resolve` both call it; the graph's `pay` and `reject` steps became one `settle_step`. | The inbox had re-implemented the end of the graph and drifted: a human reject lost the rejected lines (D4) and wrote no DECIDED event, and the inbox depended on the graph putting the escalation code first. Agent choice (docs/REFACTOR.md); rewords D19. |
| D43 | graph.py only wires steps together. `ledger.intake` checks an invoice against the ledger and records its receipt. `approval.route` takes `amount_due`, so routing a revision after payment is part of routing. `reconcile.mismatch_finding` builds ARITHMETIC_MISMATCH. | These policies were written into the graph steps: `approval.route` was not the whole routing policy, and tests had to monkeypatch it to reach some routing states. Agent choice (docs/REFACTOR.md). |
| D44 | The offline replay directory is a setting (`Settings.golden_dir`), and its index is cached on each file's size and mtime. The bank is an adapter on the graph's `Deps`, passed in with `process(..., bank=)`. The per-spec cache of CLI backends stays a module global: it deliberately accumulates usage across the calls in a process. | Tests had to patch `GOLDEN_DIR`, clear a private cache, and call `payment.pay` directly because a bank failure could not be driven through the graph. Agent choice (docs/REFACTOR.md). |
| D45 | Fixes from the review of the refactor stack. (1) A bank exception is ambiguous: the payment stays pending and goes to a person as `payment_unconfirmed`; only a definite refusal is retried. (2) Each graph run and each inbox listing sweeps pending payments older than 2 minutes into the inbox, because re-running the file is a duplicate and would never reach `pay`. (3) A revision withdraws review items but never payment items. (4) `connect` refuses a database built before D40 (`main.py reset` rebuilds it) and reindexes FOLD when Python's Unicode version changes. (5) Vendor names compare case- and space-insensitively in the duplicate check but keep NFKC differences, so a full-width or alias copy is a conflict and an all-caps copy is a duplicate. (6) The registry refuses an alias claimed by two vendors, and the rules read the same registry. (7) The inbox reports the amount actually attempted, takes a bank adapter, and resolves alias vendor names. (8) A failed or cancelled payment keeps its row as `cancelled`, and a retry reuses it. A bank success that arrives after a reviewer cancelled still marks the row sent and withdraws the queued retry, so it is never sent twice. (9) A payment that fails also closes its `payment_unconfirmed` item. (10) Each payment attempt is numbered. `start_payment` returns the number, or nothing when another process holds the row, in which case the bank is never called. Settle and fail act only on their own attempt. A success from an older attempt after a retry was sent is stored in `overpayments`, counted by `already_paid`, and queued as an `overpayment` item for a person to recover. Two sends can still happen in that race; only an idempotency key at a real bank prevents them, but the ledger now always records them. A late success counts as an overpayment only when a newer attempt is pending or sent; if the newer attempt was cancelled, the late success was the only send. Resolving an `overpayment` item records the recovery and restores `paid`; nothing is paid or rejected. A revision never withdraws an `overpayment` item. | Each one was reproduced by the fresh-context review: a stuck pending payment, a revision hiding an unconfirmed one, an upgraded database paying 1012 twice, a timeout retried into a second payment. Agent choice; corrects D40's claim about look-alikes. |

## Agent choices (not decided by David; flag if wrong)

David reviewed these on 2026-11-12: "Agreed with decisions."

- The VP critique loop and the extraction loop each allow at most 2 retries, as offered in the options David picked.
- The expected outcomes in PRD §5 become `expected_outcomes.yaml`, adjusted for D2 (1004 R1 supersedes 1004) and D10 (fraud cases escalate unless a hard rule rejects them first).
