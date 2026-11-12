# 18 — Live model pass: Grok via Cursor, Claude Haiku cross-check

**Source:** [18-live-model-pass.md](../../tickets/18-live-model-pass.md)
**Type:** AFK (subscription quota allowed by David, 2026-11-12, D31)
**Blocked by:** 09 (offline eval); 14 (adversarial rows); 15 (vision path); 17 (CLI bridge)
**Wave:** 8
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** `main.py eval --record` runs the live model over every file, writes recordings to `tests/fixtures/recorded/<backend>/` and diffs them against the goldens. A live eval on Grok 4.7 via Cursor, plus one cross-check eval on Claude Haiku via Claude Code, both with measured tokens and time.

## Context
- Why: proves the agents work against real models, honours the brief's "use Grok", and supplies real usage numbers for the ROI page.
- Constraining decisions: D31 (Grok default, Haiku cross-check, no API spend); A4 (goldens are the truth, and live differences are triaged rather than auto-accepted); D28 (fixed VP outcomes; live VP disagreement with D28 gets reported, not hidden).
- Model: start with `grok-4.7-medium-fast`. Move to `-high` only if the extraction diff shows misses, and record the reason.
- Failure paths: a live result differs from a golden → the diff report gets a per-case verdict (golden wrong → fix the golden with a reason; model wrong → fix the prompt, or log it as a known miss). A quota or rate-limit message → stop and report what remains. Never edit expected outcomes to match the model without a written reason.
- Plan anchors: PLAN §Acceptance evidence (live parity); A4; D31.

## Acceptance criteria
- [ ] Recordings for every file on Grok, plus a diff report against the goldens (docs/live/grok-diff.md) with a verdict per difference
- [ ] Live Grok eval ≥ 16/17 originals; every adversarial fraud file not paid; injection-file fields match the golden
- [ ] One live Haiku eval (cross-check) with its scorecard; Grok and Haiku differences summarised
- [ ] Live vision on the scanned 1011, or a recorded limitation if neither CLI can read images headlessly
- [ ] Tokens and seconds per invoice per backend fed to the ROI page, labelled "API-equivalent cost at published prices"

## Verification
- `uv run python main.py eval --model cli:cursor:grok-4.7-medium-fast --record && uv run python main.py eval --model cli:cursor:grok-4.7-medium-fast` — the scorecard is saved
- `uv run python main.py eval --model cli:claude:haiku` — the cross-check scorecard is saved

## Change surface
- invoice_agents/eval.py (`--record`), tests/fixtures/recorded/, docs/live/, docs/scorecard.md
- Conflict risk: low

## Out of scope
- Tuning for perfect live scores beyond prompt fixes; API-key backends

## Completion evidence
- Both live scorecards, the diff report, and the call count per backend
