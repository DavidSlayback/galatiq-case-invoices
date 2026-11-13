# AFK run report

Run started and finished on 2026-11-12 (one session, with one restart). All 19 tickets were verified and published as stacked draft PRs #1–#20 (#3 is the GitHub stack object). Per-ticket evidence is in [evidence/](evidence/); branches and PRs are in [STACK.md](STACK.md).

## Outcome

- **Offline eval:** 27/27. That is 20 brief samples, 6 adversarial invoices and 1 scan; outcomes were 9 paid, 8 rejected, 6 escalated and 4 duplicates skipped.
- **Live eval:**
  - Grok 4.7 via Cursor scored 26/27, with extraction identical on all 27. Its one miss (1012) is now routed by D33.
  - Claude Haiku scored 27/27 after three fixes (D33–D35).
- **Gate:** `scripts/check-all` passes: ruff, pyright strict, 261 tests and a check for stale goldens. Pre-commit runs the same checks.
- **Deliverables:**
  - README;
  - presentation Artifact, https://claude.ai/artifact/Uk4Fdc3Wff3zQPaVSpUghN;
  - demo video, `docs/demo/demo.mp4` (2:32);
  - dashboard screenshots in `docs/img/`.

## Verification depth

- **Full fresh-context verifier** for the parsers that take untrusted input (04 loaders, 05 extraction, 15 scans). Each first pass found real defects, all fixed with regression tests:
  - UTF-16 XML getting past the entity ban;
  - a byte-order mark emptying the CSV parse;
  - a FIFO path hanging the loader;
  - `1.234,56` parsing as 1.23;
  - accounting negatives losing their sign;
  - a 200-inch PDF page using 4.6 GB while rendering;
  - 300-page PDFs;
  - decoy text layers skipping the image path.
- **Self-check plus a mutation test on every guard** for the other tickets: each guard test was shown to fail when its guard was removed.
- **A fresh-context queue review** before the run found 14 planning defects. Among them were 1007's wrong stated total and the ±1-day terms tolerance.

## Decisions made during the run (agent; flagged for David in DECISIONS.md)

- **D25a–D30:** queue-review fixes (event types, terms tolerance, boundaries, fixed VP outcomes, payment currency, 1007's total). 1013's $50-high total was found by the code itself and added to D30.
- **D33:** vendor-master changes go to a person (both live models approved 1012).
- **D34:** re-check implausible due dates.
- **D35:** strip "(formerly X)" from vendor names.

## Human-only items left

- Done 2026-11-12: David installed `tesseract-ocr`; `scripts/check-all` now runs the local-OCR test with nothing skipped.
- An xAI API key would let the xAI API path run live; it is configured but unexercised.

## Close-out

1. **Final independent review** (a fresh-context agent over the whole stack, plus the evidence gate):
   - Every brief requirement passed, except tool use (PARTIAL: the agents use structured-output tools, not function tools) and the claims that rest only on the live runs (INCONCLUSIVE).
   - It found 11 defects, 5 of which could move money wrongly. All were fixed in PR #21 (D36–D39) with 14 regression tests.
2. **Explainer republished** at commit e6f0b66, with QA at 0 defects.
3. **Merge:** all 20 PRs merged atomically into `main` at **2b73626**. A fresh clone of `main` passes the gate (275 tests) and the offline eval at 27/27. Branches deleted. There is no remote CI (none is configured); the local gate is the CI.

## Retro

- **Independent verification paid off.** Every fresh-context review found real defects my own checks had missed: 14 at queue review, about 8 across the parser verifiers, and 11 at the final review. The vendor-key double-pay (B1) and the cross-vendor inbox approval (B3) were serious, and only an adversarial reader looking at the whole system found them. Next time, run the holistic review at the midpoint (after 10), not only at the end.
- **Live runs found design gaps, not just bugs.** The policy text's approve/reject gap and the vendor-change routing (D33) came from watching real models judge, not from the scripted goldens. One early live smoke test should be part of the first agent ticket.
- **Scripted edits drift against the formatter.** Several multi-step substitution scripts failed half-applied after ruff reformatted lines. Use the Edit tool, or re-read before scripting.
- **Mutation-checking each guard** caught one test that could not fail: the idempotency guard's first check missed because the line had been reformatted. Keep doing it.

## Follow-ups (not started)

- Purchase-order three-way match, replacing the literal stock check (D1).
- ~~An idempotency key at the bank call~~: done as the pending-payment outbox (D41, 2026-11-13).
- Agent function tools (for example, the VP looking up vendor history) if graders weight "tool use" literally.
- Auto-detect should check that a CLI is logged in before choosing it (B9; documented for now).
