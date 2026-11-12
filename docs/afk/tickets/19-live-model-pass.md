# 19 — Live model pass on Claude Haiku: record, compare, live eval

**Source:** [19-live-model-pass.md](../../tickets/19-live-model-pass.md)
**Type:** HITL
**Blocked by:** 09 (offline eval exists); 14 (adversarial rows exist); 15 (the vision path exists); human action H3 (credits and budget)
**Wave:** 8
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** `main.py eval --record` runs the live model, writes recordings beside the goldens, diffs them, and a live eval scores the originals and adversarial files with measured cost.

## Context
- Why: Proves the agents work against a real model; supplies the real cost numbers for 16 and 17.
- Constraining decisions: David (2026-11-12): no live calls unattended until API credits are sorted. Model `anthropic:claude-haiku-5-5`. The budget cap comes from H3.
- Failure paths: A live result differing from a golden → a diff report; decide golden vs prompt per case and record it in the ticket. A cost cap hit → stop and report.
- Plan anchors: PLAN §Acceptance evidence (live parity); A4

## Acceptance criteria
- [ ] Recordings for every file; a diff report against the goldens
- [ ] Live eval ≥ 16/17 originals and every adversarial row safe (no fraud file paid)
- [ ] A live vision pass on the scanned 1011
- [ ] Live extraction of the injection file matches its golden (the embedded instructions are ignored)
- [ ] Measured $ per invoice fed to the ROI page
- [ ] Total spend reported

## Verification
- `uv run python main.py eval --record && uv run python main.py eval` — the scorecard and the cost total within the cap

## Change surface
- tests/fixtures/recorded/, docs/scorecard.md, docs/STATUS.md
- Conflict risk: low

## Out of scope
- Grok (ticket 18)

## Completion evidence
- Live scorecard
- Diff report
- Spend total
