# AFK execution plan

**Source plan:** [../PLAN.md](../PLAN.md) and [../DECISIONS.md](../DECISIONS.md). Enriched tickets are in [tickets/](tickets/); the source tickets are in [../tickets/](../tickets/).

**Scope:** 19 tickets, all AFK. Tickets 01–16 build and verify the system offline against hand-written golden extractions. Ticket 17 adds the sandboxed bridge to the subscription CLIs, ticket 18 runs the live pass on Grok (with a Claude cross-check), and ticket 19 presents the result.

## Settled for this queue (David, 2026-11-12)

- No API credits. Live calls go through Cursor Pro (Grok 4.7, the default) and Claude Max (Haiku, the cross-check) via `cursor-agent -p` and `claude -p`, and are allowed unattended (D31).
- With no model configured, pick one automatically, with offline replay last (D32).
- The demo video is synthetic and agent-made (ticket 17).

## Assumptions (agent choices)

- Offline fixtures are hand-written goldens, which become the eval's truth; ticket 18 later compares live output against them (A4, revised).
- The graph skeleton in ticket 03 exposes function seams (`rules.validate`, `approval.route`, `payment.pay`, `ledger.check`), so the wave-3 lanes don't collide in `graph.py`.
- Until ticket 10 lands, the eval marks the duplicate-copy rows and the 1004 R1 row as `pending: ticket 10` rather than failing.
- Each ticket gets a stacked draft PR on its predecessor; the queue doesn't wait for review between tickets. Commits and PRs follow the attribution reminder.
- Verifier depth: a full `ticket-verifier` pass for the untrusted-parser tickets (04, 05, 14, 15); self-check plus the gate for the rest.

## Unresolved decisions

None. The only human item is the optional Tesseract install (H2 in [HUMAN-READINESS.md](HUMAN-READINESS.md)).

## Critical path

01 → 02 → 03 → 04 → 05 → 09 → 10 → 11 → 12 → 16 → 19: 11 serial tickets. Tickets 06, 07 and 08 fill parallel lanes beside 04, 15 and 17 run beside 09, 13 then 14 run beside 10 and 11, and 18 runs beside 12. None of those lengthen the critical path.

## Execution strategy

- **Single worker:** walk the queue in numeric order. It is a valid topological order: every edge points from a lower number to a higher one.
- **Parallel workers:** use the lanes in [WAVES.md](WAVES.md) and merge in its integration order.
- **Stop conditions:** a gate failure that two fix attempts can't resolve; live calls before ticket 17 lands (01–16 must stay offline); a quota or rate-limit message from either CLI.
