"""Run every sample against the expected outcomes and show the scorecard."""

import streamlit as st

from app.common import chip, settings
from invoice_agents import eval as eval_mod

s = settings()
st.title("Run all samples")
st.caption(
    "Processes every sample and adversarial invoice on a fresh database and compares each result with "
    "eval/expected_outcomes.yaml: status, who decided, and which rules must and must not fire."
)

if st.button("Run the scorecard", type="primary"):
    with st.spinner("Processing every invoice…"):
        st.session_state.rows = eval_mod.run(s)

rows = st.session_state.get("rows")
if rows:
    passed = sum(r.passed for r in rows)
    a, b, c = st.columns(3)
    a.metric("Pass", f"{passed}/{len(rows)}")
    b.metric("Paid", sum(r.actual == "paid" for r in rows))
    c.metric("Sent to a human", sum(r.actual == "escalated" for r in rows))
    st.markdown(chip("ALL PASS", "green") if passed == len(rows) else chip(f"{len(rows) - passed} FAILING", "red"))
    st.dataframe(
        [
            {
                "File": r.path.split("/")[-1],
                "Result": "PASS" if r.passed else "FAIL",
                "Expected": r.expected,
                "Actual": r.actual,
                "Decided by": r.decided_by,
                "Rules fired": ", ".join(r.rule_ids),
                "Problems": ", ".join(r.missing + [f"+{u}" for u in r.unexpected]) or (r.error or ""),
            }
            for r in rows
        ],
        hide_index=True,
        width="stretch",
    )
