# PRD: Acme Invoice Processing Agents

Status: draft for brainstorming. Requirements only, no design yet.
Source: [README.md](../README.md) at upstream `2f15015`, plus the 22 sample files in `data/invoices/`.

Each requirement is tagged with where it comes from:

- **[brief]**: stated in the README.
- **[data]**: implied by the sample invoices, though the README does not say it.
- **[inferred]**: needed for the system to be credible, but not stated anywhere. These are candidates to cut.

## 1. Problem

Acme Corp, a PE-backed manufacturer, loses about $2M a year processing invoices by hand. Invoices arrive by email as messy PDFs. Staff key in the data, check it against an inconsistent legacy inventory database, chase VP approval over email, and pay through a banking API. The result is a 30% error rate and 5-day delays. [brief]

We are building a working multi-agent prototype that runs locally and handles the whole flow: ingestion, validation, approval, and payment. [brief]

## 2. Users

| User | Needs | Source |
|---|---|---|
| AP clerk | Drop in an invoice; see what was extracted, what failed, and why | [inferred] |
| VP or approver | A short decision with its reasoning and the risk flags; a way to override | [brief] approval is simulated; override is [inferred] |
| Controller or auditor | A trail showing who or what decided each invoice, when, and on what evidence | [inferred] |
| Grader | Runs it from a fresh clone, understands it quickly, and sees agentic depth | [brief] evaluation criteria |

## 3. Functional requirements

### FR-1 Ingestion

| ID | Requirement | Source |
|---|---|---|
| FR-1.1 | Extract vendor, invoice number, dates, line items (item, quantity, unit price), subtotal, tax, total, currency, and terms into one typed schema | [brief] (vendor, amount, items, due date) and [data] (the rest) |
| FR-1.2 | Accept PDF, TXT, JSON, CSV, and XML. The CSVs come in two layouts: key-value (1006) and one row per line item (1007, 1015). One TXT is an email body (1008) | [brief] PDF and text; [data] the rest |
| FR-1.3 | Tolerate typos and OCR noise: field-name typos such as `Vndr` and `INVOCE` (1002), `O` in place of `0` (`2O26`, `$3,500.O0` in 1012), and split item names such as `Widget A` and `Gadget X` (1012) | [brief] and [data] |
| FR-1.4 | Normalise dates (`Jan 30 2026`, `01/28/2026`, `26-Jan-2O26`, `January 27, 2026`) and treat unparseable values (`yesterday` in 1003) as errors, not guesses | [data] |
| FR-1.5 | Report missing or empty fields explicitly; never fill them with invented values (1009 has an empty vendor and a null due date) | [brief] and [data] |
| FR-1.6 | Map item names to canonical inventory SKUs (`Widget A` → `WidgetA`; `WidgetA (rush order)` → `WidgetA`) and keep the raw text | [data] |
| FR-1.7 | Give each extracted field a confidence score or provenance, so later stages can tell a parse from a guess | [inferred] |
| FR-1.8 | Self-correct: check the extraction against itself (line totals, subtotal, tax, total) and re-extract or flag when it does not reconcile | [brief] (self-correction loops) |

### FR-2 Validation

| ID | Requirement | Source |
|---|---|---|
| FR-2.1 | Create and seed a SQLite inventory database: WidgetA 15, WidgetB 10, GadgetX 5, FakeItem 0 | [brief] |
| FR-2.2 | Flag a quantity above stock (1002: 20 × GadgetX against 5 in stock) | [brief] |
| FR-2.3 | Flag zero-stock or suspicious items (1003: FakeItem) | [brief] |
| FR-2.4 | Flag items missing from inventory (1008: SuperGizmo and MegaSprocket; 1016: WidgetC) | [brief] |
| FR-2.5 | Flag data-integrity errors: negative quantity, and a total that disagrees with the line items (1009: subtotal 1000, line items sum to −250, total −250) | [brief] and [data] |
| FR-2.6 | Add up all lines for the same SKU before checking stock. Every individual line of 1013 passes, but the totals do not: WidgetA 22 > 15, WidgetB 18 > 10, GadgetX 9 > 5. 1010 lists WidgetA twice | [data] |
| FR-2.7 | Check the arithmetic: line total = quantity × price, the lines sum to the subtotal, and subtotal + tax + shipping = total (1010 includes shipping) | [data] |
| FR-2.8 | Flag unit prices that differ from the catalog: a rush premium (1010, $300 against $250), volume discounts (1013), and EUR prices (1014) | [data]; needs a price column, which the brief permits |
| FR-2.9 | Flag currencies other than USD (1014 is in EUR) | [data] |
| FR-2.10 | Detect duplicates and revisions: the same invoice number twice (1004 and its R1 revision), and the same invoice in two formats (1011, 1012 and 1013 each have both a PDF and a TXT or JSON copy). Never pay the same invoice twice | [data] |
| FR-2.11 | Flag date problems: due date already past or equal to the invoice date (1002, 1008); due date that disagrees with the terms (1001 is Net 15 from Jan 15 with a due date of Feb 1; 1002 is Net 30 with a due date equal to the invoice date) | [data] |
| FR-2.12 | Score vendor risk: unknown vendors, a renamed vendor (1012, "formerly FastShip"), implausible addresses (1005 gives 1600 Pennsylvania Ave), and pressure language (1003: "URGENT", "Wire transfer preferred") | [data]; needs a vendor table, which the brief permits |
| FR-2.13 | Catch the stock overruns that the README's scenario table leaves out: 1005 (GadgetX 8 > 5), 1007 (WidgetA 20 > 15, WidgetB 15 > 10) and 1013 (see FR-2.6) | [data] |

### FR-3 Approval

| ID | Requirement | Source |
|---|---|---|
| FR-3.1 | Simulate a VP review that applies rules, for example extra scrutiny above $10K | [brief] |
| FR-3.2 | Have the LLM reason toward approve or reject, then critique its own decision before finalising it | [brief] |
| FR-3.3 | Base the decision on the validation findings and record which rules fired | [brief] and [inferred] |
| FR-3.4 | Add an "escalate to a human" outcome alongside approve and reject | [inferred] |
| FR-3.5 | Treat totals just under the threshold as a signal of possible threshold-gaming (1012 is $9,975; 1008 is $9,900) | [data] and [inferred] |
| FR-3.6 | Never let the LLM approve an invoice that a hard rule rejected (a guardrail) | [inferred] |

### FR-4 Payment

| ID | Requirement | Source |
|---|---|---|
| FR-4.1 | Call `mock_payment(vendor, amount)` when an invoice is approved | [brief] |
| FR-4.2 | Log every rejection with its reasoning | [brief] |
| FR-4.3 | Make payment idempotent: one payment per invoice number and revision, keyed in the ledger | [data] (duplicates) |
| FR-4.4 | Simulate payment failures and retries | [inferred] |

### FR-5 Orchestration and interface

| ID | Requirement | Source |
|---|---|---|
| FR-5.1 | Multiple agents with a framework (LangGraph, CrewAI, AutoGen) or a custom orchestrator | [brief] |
| FR-5.2 | Tool calls, structured outputs, and self-correction loops | [brief] |
| FR-5.3 | Command line: `python main.py --invoice_path=...` | [brief] |
| FR-5.4 | Structured logs and results as output | [brief] |
| FR-5.5 | Batch mode: process a whole directory and print a summary table | [inferred]; needed for the demo and for cross-invoice duplicate checks |
| FR-5.6 | A UI that users "understand and enjoy" | [brief] (evaluation criteria) |
| FR-5.7 | Grok as the reasoning engine; any other model is allowed | [brief] |

## 4. Non-functional requirements

| ID | Requirement | Source |
|---|---|---|
| NFR-1 | Runs locally with no internet for external APIs; all services simulated | [brief] |
| NFR-2 | Python is the preferred language | [brief] |
| NFR-3 | No cloud deployment | [brief] |
| NFR-4 | Clean, testable code with error handling and observability | [brief] |
| NFR-5 | Deterministic and auditable: the same input and seed give the same decision. Hard rules sit in code, not in the prompt | [inferred] |
| NFR-6 | Testable without network access: a scripted offline model or recorded LLM responses, so the test suite runs with no API key | [inferred]; resolves the conflict between NFR-1 and FR-5.7 |
| NFR-7 | Safe by default: anything that is malformed, ambiguous, or uncertain gets escalated or rejected, never paid | [inferred] |
| NFR-8 | Treat invoice text as untrusted: prompt injection inside an invoice must not change the decision | [inferred]; 1003's "pay immediately" is a mild case |
| NFR-9 | Trace every stage: inputs, outputs, tool calls, retries, LLM tokens and latency | [brief] (observability) |
| NFR-10 | Set up from a fresh clone in one command | [brief] (shipping mindset) |
| NFR-11 | Show a per-invoice cost and processing time, so the case can point to the $2M a year and the 5-day delay | [brief] (presentation, business impact) |
| NFR-12 | Public GitHub repository | [brief] |

## 5. Expected outcome per invoice

These are draft expected outcomes for the test oracle, still to be confirmed when we brainstorm.

| Invoice | Format | Key issues | Draft outcome |
|---|---|---|---|
| 1001 | TXT | Clean; due date disagrees with Net 15 by 2 days | Approve, with a minor flag |
| 1002 | TXT, typos | GadgetX 20 > 5; $15K; due = invoice date | Reject |
| 1003 | TXT | FakeItem at zero stock; $100K; "yesterday"; urgency and wire-transfer language | Reject as suspected fraud |
| 1004 | JSON | Clean | Approve, unless R1 supersedes it |
| 1004 R1 | JSON | Same number, revised; adds GadgetX 5 (exactly at stock) | Supersedes 1004; pay at most once |
| 1005 | JSON | GadgetX 8 > 5; $15.2K; White House address | Reject or escalate |
| 1006 | CSV key-value | Clean | Approve |
| 1007 | CSV rows | WidgetA 20 > 15, WidgetB 15 > 10; $15.5K | Reject |
| 1008 | Email TXT | Unknown items; $9.9K, just under the threshold; past due | Reject |
| 1009 | JSON | Empty vendor, negative quantity, totals disagree, no due date | Reject (data integrity) |
| 1010 | TXT table | WidgetA appears twice (12 in total, fine); rush price premium; shipping line | Approve or escalate (price variance) |
| 1011 | PDF and TXT | Clean; two copies | Approve once; second copy flagged as a duplicate |
| 1012 | PDF and TXT | OCR noise; vendor renamed; $9,975 | Escalate (vendor change, near threshold) |
| 1013 | PDF and JSON | Each line fits stock, the summed totals do not; $22.6K | Reject; second copy is a duplicate |
| 1014 | XML | EUR; prices below catalog | Escalate (currency) |
| 1015 | CSV rows | Clean | Approve |
| 1016 | JSON | WidgetC unknown; known vendor | Reject, or partial approval |

Note: if stock is consumed as a batch is processed, the order matters. 1001, 1004 and 1006 together use 18 WidgetA against 15 in stock. See B-3.

## 6. Questions to brainstorm

### Domain semantics: these change the core logic

- **B-1 What does "stock" mean?** Acme is buying from these vendors, so an invoice that asks for more than Acme holds in stock is not wrong in itself. The brief treats it as wrong anyway. Options: (a) take the brief literally; (b) reinterpret the table as purchase orders and goods received, which makes this a three-way match; (c) take it literally and record the reinterpretation as an assumption that would extend the system later. Recommended for grilling: (c).
- **B-2 Revisions and duplicates.** Does R1 replace 1004, or add to it? Is a PDF and TXT pair the same invoice? Which file wins?
- **B-3 Is stock stateful?** Should approved invoices reduce stock, so that the order of a batch matters? Or is every invoice checked against the stock as seeded?
- **B-4 Partial approval.** Pay the valid lines of 1016 and hold WidgetC, or reject the whole invoice?
- **B-5 Currency.** Convert EUR using a fixed mock rate, or always escalate?
- **B-6 Price tolerance.** How far can a unit price differ from the catalog (discount, rush, foreign currency) before we flag it?
- **B-7 The approval policy beyond $10K.** Tiers ($10K and $50K?), vendor risk, past-due dates, and the near-threshold signal.

### Architecture

- **B-8 Orchestration.** LangGraph (explicit state machine, checkpoints, easy to draw), CrewAI or AutoGen (more "agentic", less control), or custom (smallest, but looks less like a framework). The graders reward agentic sophistication and code quality at the same time.
- **B-9 Where the LLM decides and where code decides.** Rules belong in code; the LLM handles extraction and narrative judgement. How much does the LLM actually decide?
- **B-10 Ingestion strategy.** A deterministic parser for each format with the LLM as fallback, or the LLM for everything with a schema check? This trades cost and determinism against the "agentic" look.
- **B-11 Shape of the self-correction loops.** Extraction loops back on reconciliation errors. Approval loops between a proposer and a critic. What are the iteration caps, and what stops the loop?
- **B-12 Model.** Grok (do you have a key?), or a local or alternative model behind one interface, plus a scripted offline client for tests. The README's `from xai import Grok` snippet and the `grok.x.ai` URL look out of date; check the current xAI SDK before relying on them.
- **B-13 PDF stack.** pdfplumber or PyMuPDF for text. All three PDFs here have a text layer. Do we also need OCR for scanned images?

### Product and presentation

- **B-14 UI.** Options: a rich terminal UI (Textual or Rich), Streamlit, or a small FastAPI app with an HTMX dashboard. Should it have an approval inbox, a per-invoice trace view, and a "why" panel? Note: you prefer avoiding JavaScript, and that favours Textual or Streamlit.
- **B-15 Going beyond the brief.** Candidates: a vendor risk score, a duplicate and revision ledger, a human override, a replay or trace viewer, a cost and latency dashboard, adversarial test invoices (prompt injection, near-threshold), an eval harness that scores the outcomes in §5, and an email-ingest simulator.
- **B-16 Business-impact story.** Measure time per invoice, cost per invoice, and catch rate on the trap cases, then project against the $2M and 5-day baseline.
- **B-17 How far to cut.** What is the minimum loveable demo? Options include dropping XML and email intake, dropping partial approval, and leaving out a live UI.

## 7. Out of scope (proposed)

Real email or banking integrations, cloud deployment, multiple tenants, authentication, and a real ERP or procurement system. Pending agreement.
