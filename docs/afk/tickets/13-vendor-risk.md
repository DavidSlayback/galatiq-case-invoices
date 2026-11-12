# 13 — Vendor registry matching and risk score

**Source:** [13-vendor-risk.md](../../tickets/13-vendor-risk.md)
**Type:** AFK
**Blocked by:** 09 (the risk score changes expected outcomes; the eval guards it)
**Wave:** 6
**Lane:** vendors
**Verifier profile:** self-check
**What it delivers:** Vendor matching (exact, alias, lookalike) and a 0–100 risk score from weighted signals, surfaced in the findings, the VP context and the CLI.

## Context
- Why: D9, D10, FR-2.12.
- Constraining decisions: D9 seeds (see 02). D10: fraud signals escalate, never auto-reject. Lookalike = normalised edit distance ≤ 2 to a known vendor without being an exact or alias match → LOOKALIKE_VENDOR (fraud). Alias match → VENDOR_RENAMED (soft). Score ≥ 60 → HIGH_VENDOR_RISK (fraud).
- Failure paths: A blank vendor → handled by MISSING_VENDOR, and risk is not double-counted. Unicode homoglyphs → NFKC-normalise first.
- Plan anchors: PRD FR-2.12; D9, D10

## Acceptance criteria
- [ ] 1003 and 1005 score ≥ 60; 1001 < 20
- [ ] 1012 matches FastShip through the alias → VENDOR_RENAMED
- [ ] 'Widgets lnc.' → LOOKALIKE_VENDOR
- [ ] The VP agent's context includes the score and signals
- [ ] Eval rows updated and passing

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run python main.py eval --offline` — exit 0

## Change surface
- invoice_agents/vendors.py, invoice_agents/rules.py (registration only), invoice_agents/agents/vp.py (context), invoice_agents/cli.py and inbox list (risk column), eval/expected_outcomes.yaml, tests/test_vendors.py
- Conflict risk: medium: the yaml is shared with 10; merge 10 first

## Out of scope
- Bank-detail checks need bank data on the invoice; covered by the adversarial file in 14

## Completion evidence
- Score table for all vendors
