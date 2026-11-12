"""Human review of escalated invoices."""

import contextlib
import io

import streamlit as st

from app.common import chip, conn, settings
from invoice_agents import inbox

s = settings()
c = conn(s)
st.title("Review inbox")
st.caption("Invoices the agents would not settle on their own. Every decision needs a note and is logged.")

if msg := st.session_state.pop("inbox_msg", None):
    st.success(msg)

items = inbox.list_open(c)
if not items:
    st.info("Nothing waiting for review. Process an invoice that needs judgement, such as invoice_1012.txt.")

for it in items:
    label = chip(it.label.upper(), "red") + " " if it.label else ""
    amount = f"{it.amount_due} due (revision delta)" if it.amount_due else f"{it.total or '-'} {it.currency or ''}"
    with st.container(border=True):
        st.markdown(f"### {label}{it.key.invoice_number} · {it.key.vendor}")
        cols = st.columns(3)
        cols[0].metric("Amount", amount)
        # Plain text, not a metric: reasons like "fraud signals: PROMPT_INJECTION" are too long for one.
        cols[1].markdown(f"Why it is here\n\n**{it.reason.replace('_', ' ')}**")
        cols[2].metric("Vendor risk", f"{it.risk}/100" if it.risk is not None else "-")
        if it.flags:
            st.markdown("**Flags:** " + "  ".join(chip(f, "orange") for f in it.flags))
        if it.reasoning:
            st.markdown("**Agents' reasoning:** " + " ".join(it.reasoning))
        with st.form(f"decide-{it.id}"):
            note = st.text_input(
                "Note (required)", key=f"note-{it.id}", placeholder="e.g. Confirmed the rename with FastShip by phone"
            )
            a, r = st.columns(2)
            approve = a.form_submit_button("Approve and pay", type="primary")
            reject = r.form_submit_button("Reject")
            if approve or reject:
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        res = inbox.resolve(
                            c, it.key.invoice_number, approve=approve, note=note, reviewer="human:ui", inbox_id=it.id
                        )
                    st.session_state.inbox_msg = f"{it.key.invoice_number}: {res['status']} {res.get('amount', '')}"
                    st.rerun()
                except inbox.InboxError as e:
                    st.error(str(e))
