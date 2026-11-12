# AFK execution plan

**Source plan:** [../PLAN.md](../PLAN.md) and [../DECISIONS.md](../DECISIONS.md). Enriched tickets are in [tickets/](tickets/); the source tickets are in [../tickets/](../tickets/).

**Scope:** 19 tickets: 17 AFK and 2 HITL (18 Grok switch, 19 live-model pass). The AFK queue builds and verifies the whole system offline, against hand-written golden extractions. Nothing in it calls a live model.

## Settled for this queue (David, 2026-11-12)

- The stand-in model is `anthropic:claude-haiku-5-5` (A2).
- No live model calls unattended; API credits may be on another account. The live checks are collected into HITL ticket 19.
- The demo video is synthetic and agent-made (ticket 17).

## Assumptions (agent choices)

- Offline fixtures are hand-written goldens, which become the eval's truth; ticket 19 later compares live output against them (A4, revised).
- The graph skeleton in ticket 03 exposes function seams (`rules.validate`, `approval.route`, `payment.pay`, `ledger.check`), so the wave-3 lanes don't collide in `graph.py`.
- Until ticket 10 lands, the eval marks the duplicate-copy rows and the 1004 R1 row as `pending: ticket 10` rather than failing.
- Each ticket gets a stacked draft PR on its predecessor; the queue doesn't wait for review between tickets. Commits and PRs follow the attribution reminder.
- Verifier depth: a full `ticket-verifier` pass for the untrusted-parser tickets (04, 05, 14, 15); self-check plus the gate for the rest.

## Unresolved decisions

None block the AFK queue. H1–H3 in [HUMAN-READINESS.md](HUMAN-READINESS.md) block only tickets 18 and 19 (and the optional Tesseract path in 15).

## Critical path

01 → 02 → 03 → 04 → 05 → 09 → 10 → 11 → 12 → 16 → 17: 11 serial tickets. Tickets 06, 07 and 08 fill parallel lanes beside 04, ticket 15 runs beside 09, and 13 then 14 run beside 10 and 11. None of those lengthen the critical path.

## Execution strategy

- **Single worker:** walk the queue in numeric order. It is a valid topological order.
- **Parallel workers:** use the lanes in [WAVES.md](WAVES.md) and merge in its integration order.
- **Stop conditions:** a gate failure that two fix attempts can't resolve; any need for a live model call; reaching ticket 18 or 19.
