"""Event timeline and agent traces for one invoice."""

import streamlit as st

from app.common import conn, conversation, settings, trace

s = settings()
c = conn(s)
st.title("History")
st.caption("The append-only event ledger: every receipt, duplicate, revision, decision and payment.")

numbers = [r[0] for r in c.execute("SELECT DISTINCT invoice_number FROM invoice_events ORDER BY invoice_number")]
if not numbers:
    st.info("No invoices processed yet.")
    st.stop()
number = st.selectbox("Invoice", numbers)
rows = c.execute("SELECT * FROM invoice_events WHERE invoice_number=? ORDER BY id", (number,)).fetchall()
st.dataframe(
    [
        {
            "When (UTC)": r["ts"][:19].replace("T", " "),
            "Rev": r["revision"],
            "Event": r["event"],
            "Actor": r["actor"],
            "Details": r["payload"][:200],
        }
        for r in rows
    ],
    hide_index=True,
    width="stretch",
)
for run_id in dict.fromkeys(r["run_id"] for r in rows):
    lines = trace(s, run_id)
    if lines:
        with st.expander(f"How the agents decided, run {run_id}"):
            conversation(lines)
            st.caption("Raw trace")
            st.json(lines, expanded=False)
