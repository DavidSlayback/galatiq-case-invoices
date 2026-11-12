# 18 — Switch the default model to Grok

**Source:** [18-grok-switch.md](../../tickets/18-grok-switch.md)
**Type:** HITL
**Blocked by:** 19 (the live harness and its budget must be proven on Haiku first); also human actions H1, H3
**Wave:** 9
**Lane:** serial-required
**Verifier profile:** self-check
**What it delivers:** Grok is the default model, the live eval passes on it, and the README names it.

## Context
- Why: The brief prefers Grok; D12.
- Constraining decisions: D12. HITL: needs XAI_API_KEY (H1) and a budget (H3). Check the current xAI model ID and SDK via primary docs at implementation time; the README's `from xai import Grok` snippet looks out of date.
- Failure paths: Grok output differs from the goldens → triage: fix the prompt or golden, never the expected outcome without a reason.
- Plan anchors: D12

## Acceptance criteria
- [ ] `INVOICE_MODEL=<grok id>` live eval ≥ 16/17 originals
- [ ] README model section updated

## Verification
- `uv run python main.py eval` — ≥ 16/17 PASS, cost under the H3 cap

## Change surface
- invoice_agents/settings.py, .env.example, README.md
- Conflict risk: low

## Out of scope
- Changing goldens to match Grok without a recorded reason

## Completion evidence
- Live scorecard
- Cost line
