# Live model results

Every sample and adversarial invoice (27 files) run against real models through the subscription CLIs (D31), 2026-11-12. Scorecards: [Grok](scorecard-grok.md) · [Haiku](scorecard-haiku.md). Each extraction is recorded under `fixtures/recorded/<backend>/`.

| Backend | Result | Core fields vs goldens | Calls | Tokens | Time |
|---|---|---|---|---|---|
| Grok 4.7 medium-fast via Cursor (`cli:cursor:grok-4.7-medium-fast`) | 26/27 on the first pass; the only miss was 1012, now routed by D33 | identical on all 27 | 42 | 573,905* | 11.7 min |
| Claude Haiku via Claude Code (`cli:claude:haiku`), first pass | 24/27 | 2 differences, both fixed (see below) | 45 | 43,310 | 4.4 min |
| Claude Haiku, after the fixes | **27/27** | identical on all 27 | 40 | 37,600 | 3.5 min |

\* Cursor counts its own agent prompt in the input tokens. The Claude runs use our system prompt with tools off.

## What the live pass covered that offline replay cannot

- **Vision.** The scanned 1011 has no text layer. Both CLIs read the page image: Claude with only its `Read` tool, Cursor in read-only ask mode. Both extractions matched the golden.
- **Prompt injection.** Both models copied the injected instructions into `notes` as data, and their extractions matched the golden. The `PROMPT_INJECTION` rule then routed the invoice to a human, as code, whatever the model did.
- **Self-correction loops** ran on real outputs: 1007, 1009 and 1013 keep their wrong stated totals through the retries and end in `ARITHMETIC_MISMATCH`.

## What it found, and the fixes

| Found | Cause | Fix |
|---|---|---|
| 1012: both models' VP approved and the critic agreed (D28 expected a deadlock) | The registry links QuickShip to FastShip, so approval is defensible model judgement | **D33:** a vendor-master change (rename) goes straight to a person. It is not something for an agent to judge |
| Haiku: 1012's TXT copy was not caught as a duplicate | The vendor came back as "QuickShip Distributers (formerly FastShip Ltd.)", which changed the ledger key | **D35:** the normaliser moves "(formerly X)" into notes |
| Haiku: due date read as 2027-02-27 on the control invoice | A misread year, which arithmetic cannot catch | **D34:** a due date more than 45 days off the terms triggers one more extraction (never a finding by itself) |
| Smoke run: VP rejected an immaterial, unexplained flag | Gap in the policy text (see [smoke.md](smoke.md)) | The review policy now judges flags on materiality |

Grok was not re-run after the fixes. Its extractions already matched every golden, and its only miss (1012) is now decided by a deterministic routing rule, not a model.

## Cost (API-equivalent)

The subscriptions bill no per-call dollars. At published API prices (third-party aggregators, 2026-11-12; not confirmed on the vendors' own pages):
- **Grok 4.7** at $2 per million input and $6 per million output tokens: about **$1.20** for all 27 invoices, roughly 4.4¢ each.
- **Haiku 5.5** at $0.10 per million input and $0.50 per million output: well **under 1¢** for the whole run.
