# 07 · Tier routing, VP agent, critic loop and guardrail

- **Blocked by:** 03
- **Source:** FR-3.*, D7, D10, D15
- **Status:** todo

## What
Routing: any hard finding → reject. Any fraud finding or total over $50K → human inbox with a 'suspected fraud' label where relevant. Total of $10K–$50K or any soft finding → VP review. Otherwise auto-approve. The VP agent outputs a `Proposal(decision, reasons, cited_rule_ids)`; the critic outputs `Critique(agrees, objections)`. If they still disagree after 2 rounds → inbox. Guardrail in code: any `approve` when a hard finding exists is coerced to `reject` and logged as a `guardrail_override` event. Offline fixtures cover the VP and critic.

## Surfaces
invoice_agents/approval.py, invoice_agents/agents/{vp,critic}.py, tests/test_approval.py

## Acceptance
- [ ] Table test for routing across the D7 boundaries
- [ ] A scripted VP that approves an invoice with a hard finding is overridden to reject
- [ ] A scripted disagreement for 2 rounds goes to the inbox

## Verify
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
```

## Docs
README: approval policy table
