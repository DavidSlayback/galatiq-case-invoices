"""Human review of escalated invoices."""

import contextlib
import io

import streamlit as st

from app.common import chip, conn, md, settings
from invoice_agents import inbox

CHANGE_LABEL = {"confirmed_name": "add confirmed name", "bank_ref": "replace bank details with"}
# (approve label, reject label, help) by inbox reason: approving a payment item sends nothing new.
DEFAULT_BUTTONS = ("Approve and pay", "Reject", "")
BUTTONS = {
    "payment_unconfirmed": (
        "Confirm it reached the bank",
        "Not at the bank: cancel",
        "Check the bank first. Confirming records the payment without sending it again;"
        " cancelling queues a retry for review.",
    ),
    "overpayment": (
        "Record recovery",
        "Close (also records recovery)",
        "This payment left twice. Either button records that the extra amount is being recovered; nothing is paid.",
    ),
    "payment_failed": ("Approve and retry payment", "Reject", ""),
}

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
        st.markdown(f"### {label}{md(it.key.invoice_number)} · {md(it.key.vendor)}")
        cols = st.columns(3)
        cols[0].metric("Amount", amount)
        # Plain text, not a metric: reasons like "fraud signals: PROMPT_INJECTION" are too long for one.
        cols[1].markdown(f"Why it is here\n\n**{it.reason.replace('_', ' ')}**")
        cols[2].metric("Vendor risk", f"{it.risk}/100" if it.risk is not None else "-")
        if it.flags:
            st.markdown("**Flags:** " + "  ".join(chip(f, "orange") for f in it.flags))
        if it.reasoning:
            st.markdown("**Agents' reasoning:** " + md(" ".join(it.reasoning)))
        with st.form(f"decide-{it.id}"):
            note = st.text_input(
                "Note (required)", key=f"note-{it.id}", placeholder="e.g. Confirmed the rename with FastShip by phone"
            )
            yes, no, help_text = BUTTONS.get(it.reason, DEFAULT_BUTTONS)
            if help_text:
                st.caption(help_text)
            learn = False
            if it.vendor_changes:  # D50, D52: a rename or new bank details, never beside another fraud signal
                learn = st.checkbox(
                    "I verified this with the vendor: also update the vendor record",
                    key=f"learn-{it.id}",
                    help="Applies every change listed below, so the vendor's next invoice is not flagged for it"
                    " again. Logged with your note. Only applies when you approve.",
                )
                for ch in it.vendor_changes:
                    st.caption(f"{md(ch['vendor'])}: {CHANGE_LABEL[ch['field']]} → {md(ch['value'])}")
            a, r = st.columns(2)
            approve = a.form_submit_button(yes, type="primary")
            reject = r.form_submit_button(no)
            if approve or reject:
                try:
                    with contextlib.redirect_stdout(io.StringIO()):  # mock_payment prints to the server console
                        res = inbox.resolve(
                            c, it.key.invoice_number, approve=approve, note=note, reviewer="human:ui",
                            inbox_id=it.id, update_vendor=learn and approve,
                        )  # fmt: skip
                    st.session_state.inbox_msg = f"{it.key.invoice_number}: {res['status']} {res.get('amount', '')}"
                    st.rerun()
                except inbox.InboxError as e:
                    st.error(str(e))
