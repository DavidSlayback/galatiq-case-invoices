# Deepening refactor (2026-11-13)

Source: the architecture review at https://claude.ai/artifact/FF6ru9BpNsAmBXkUeW6Drh. David picked candidates 1–5 ("1-5"; implement mode, so no grilling). They land as stacked PRs, one candidate each. Each PR must keep the gate (`scripts/check-all`) and the offline eval (27/27) green, and each is tested through the deepened module's interface.

The interface choices below were made by the agent while implementing, as the skill's implement mode allows. Each is recorded with its reason.

| # | Deepened module | Interface decision (agent) | Why |
|---|---|---|---|
| 1 | `identity.py`: invoice identity | One `fold` rule (NFKC, casefold, collapsed spaces), registered as SQLite collation `FOLD` on every table key column. `key_for` resolves an exact or alias vendor to its registered name; look-alikes are not resolved. Conflict copies are named and recognised only here. User-typed numbers go through `lookup_number`. | A collation makes every existing query fold identically, with no extra key columns to keep in sync. A look-alike must never inherit a real vendor's ledger. |
| 2 | `db.py`: store transitions | Payments write a `pending` row before the bank call and settle it afterwards. Withdraw, findings and inbox-resolve each run in one transaction. A pending row found later is never re-sent; it goes to the inbox as `payment_unconfirmed`. | A crash after the bank call leaves evidence instead of a gap, and a human checks the bank. |
| 3 | `settle.py`: settlement | `settle(conn, key, decision, ...)` applies the guardrail, writes DECIDED, and then pays or rejects (with the bad lines). The graph's `pay` and `reject` nodes become one `settle` node, and `inbox.resolve` calls the same function. | One policy and one audit trail, whoever decides. D19 is reworded to match. |
| 4 | `ledger.intake`, `approval.route` | The ledger exposes a single intake operation that checks and records. `route` takes `amount_due`, so revision-after-payment routing lives in approval. `reconcile` builds ARITHMETIC_MISMATCH. | graph.py becomes wiring only. |
| 5 | `Deps` adapters | The replay source directory is a Settings field, cached per directory. The bank is a field on `Deps`, and `process(..., bank=)` passes it through. | Tests swap adapters without patching module globals. |

## Status

- [x] 1 identity: D40. 1012 is now keyed and paid under FastShip Ltd. (its registered name); gate and eval 27/27 pass; the `NOCASE` mutation fails 2 tests.
- [x] 2 store transitions: D41. Crash, rollback and migration tests; writing the pending row after the bank call fails 4 tests; gate and eval 27/27 pass.
- [x] 3 settlement: D42; D19 reworded. Human decisions now write DECIDED (the inbox tests were updated to expect it); gate and eval 27/27 pass.
- [x] 4 graph policy: D43. graph.py went from 495 to 395 lines; the guardrail test that monkeypatched `route` was replaced by `test_settle`; gate and eval 27/27 pass.
- [x] 5 adapters: D44. No test patches GOLDEN_DIR or clears a private cache; a bank failure now runs through the graph in a test; gate and eval 27/27 pass.
- [x] Fresh-context review of the stack. It found 9 defects plus 3 minor ones, 3 of which could move money (pending payments never recovered, a revision hiding an unconfirmed payment, an upgraded database paying an alias twice). All were fixed on `refactor/6-review-fixes` (D45) with regression tests in `tests/test_review_fixes.py`, and mutation-checked. The re-check found one new double-send (sweep, then cancel, then a late bank success) and an orphaned inbox item. Both are fixed: R11 and R12. Removing cancel-not-delete fails R11. The third check found that a concurrent claim silently passed the upsert (R13) and that a late success after a retry went unrecorded (R14). Both are fixed with attempt numbers and an `overpayments` table; ignoring the attempt number fails R14. The fourth check found three problems with overpayment items: they were resolved through settlement (O1), withdrawn by a revision (O2), and raised falsely after a declined retry (O3, R15). All are fixed; without the cancelled-row condition, R15 fails.
- [x] Fifth check: O1–O3 hold. One more interleaving gave a false recovery item: attempt 1 landed late while the retry was pending, and the retry was then declined. Fixed: `fail_payment` promotes the earlier attempt's overpayment to the real payment, and settling is idempotent per attempt (R16; disabling the promotion fails R16).
- [x] Stopped the review loop at convergence. Each round found a narrower interleaving of the same retry and cancel race, and every money case has a regression test that fails under mutation. Remaining risk: interleavings of three or more attempts are not tested. A real bank's idempotency key closes the whole class and is the production fix (docs/afk/REPORT.md follow-ups).
- [ ] Merge the stack.

A database built before D40 is refused with a message to run `main.py reset`. `connect` adds `payments.status` to a D40-era database in place. External SQLite tools must register the `FOLD` collation (`identity.register`) before they can filter or write the key columns; an unfiltered `SELECT` works without it.
