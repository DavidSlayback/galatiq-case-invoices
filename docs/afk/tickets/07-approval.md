# 07 — Tier routing, VP agent, critic loop and guardrail

**Source:** [07-approval.md](../../tickets/07-approval.md)
**Type:** AFK
**Blocked by:** 03 (needs the approval.route seam and graph branches)
**Wave:** 3
**Lane:** approval
**Verifier profile:** self-check
**What it delivers:** Routing per D7. A VP agent and a critic agent loop for up to 2 rounds; disagreement goes to the inbox, and a code guardrail coerces any approval with hard findings to a rejection.

## Context
- Why: FR-3; the brief's reflection/critique loop; NFR-7.
- Constraining decisions: D7 tiers: hard → reject; fraud or >$50K → human with a 'suspected fraud' label when fraud (D10); $10K–$50K or soft → VP; else auto. D15: the VP proposes with cited rule IDs and a separate critic checks; single-agent self-reflection was rejected as a weaker check. The guardrail is in code, not the prompt (FR-3.6). The VP and critic offline use scripted FunctionModels with per-invoice golden responses.
- Failure paths: The VP cites a rule ID that doesn't exist → critic objection plus a retry. The model returns invalid structured output → PydanticAI retry, then escalate. Disagreement after round 2 → inbox, never a default approval.
- Plan anchors: PRD FR-3; D7, D10, D15

## Acceptance criteria
- [ ] Table test across the boundaries $9,499.99/$9,500/$10,000/$50,000/$50,000.01 with and without each severity
- [ ] A scripted VP approving with a hard finding → reject plus a `guardrail_override` event
- [ ] Scripted disagreement for 2 rounds → inbox, with both transcripts stored in the JSONL trace
- [ ] The decision event payload contains cited_rule_ids and the critic verdicts
- [ ] Edits graph.py only to fill the VP branch

## Verification
- `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q` — exit 0, no failures
- `uv run pytest -q tests/test_approval.py` — routing table plus guardrail plus loop tests pass

## Change surface
- invoice_agents/approval.py, invoice_agents/agents/{vp,critic}.py, invoice_agents/graph.py (VP branch only), tests/test_approval.py, tests/fixtures/golden/vp/
- Conflict risk: medium: the only wave-3 ticket allowed to touch graph.py

## Out of scope
- Human inbox commands (ticket 11)
- Vendor risk input to the VP (ticket 13)

## Completion evidence
- Routing table test output
- A guardrail event example
