# Live smoke test: subscription CLI backends

Invoice 1001 run through the real CLIs on 2026-11-12. Both use subscription quota, not API credit (D31).

| Backend | Wall time | Extraction | Decision |
|---|---|---|---|
| `cli:cursor:grok-4.7-low-fast` (Cursor Pro) | 1m58s | correct; same finding as offline (`DUE_TERMS_MISMATCH` +2 days) | escalated: VP and critic deadlocked |
| `cli:claude:haiku` (Claude Max) | 52s | correct; same finding | escalated: VP and critic deadlocked |
| `cli:claude:haiku` after the policy fix | — | correct | **approved by vp_agent** ("the flag is immaterial … a later due date only benefits Acme") |

## What the first runs exposed

Both models found a real gap in the review policy text. The policy said to approve only when every flag has a documented explanation, and to reject only when the invoice should not be paid as issued. An unexplained but harmless +2-day terms gap matches neither rule.

So the VP rejected, and the critic correctly objected that "unexplained" is not one of the reasons to reject. After two rounds the invoice went to a human. The extraction, the rules and the loop mechanics all behaved correctly.

**Fix:** the policy in `agents/reviewers.py` now judges each flag on materiality: "does it change whether Acme should pay this amount to this vendor?" It gives examples on both sides. On the re-run, Haiku approved 1001 as D28 expects.

The live eval over every file (Grok as the default, with a Haiku cross-check) is ticket 18.
