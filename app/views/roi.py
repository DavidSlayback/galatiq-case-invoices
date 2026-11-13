"""Business impact: measured behaviour on the test set, projected over editable, labelled assumptions."""

import streamlit as st

from app.common import settings
from invoice_agents import eval as eval_mod
from invoice_agents.roi import Assumptions, Measured, project

s = settings()
st.title("Business impact")
st.caption(
    "Measured numbers come from running the system. Everything marked **assumption** is an input you can change; "
    "the brief gives no invoice volume, so none is presented as fact."
)


@st.cache_data(show_spinner="Scoring the test invoices…")
def measured_from_eval() -> tuple[float, float, int]:
    """Escalation rate and trap-catch rate from the offline eval of all test invoices."""
    rows = eval_mod.run(s.with_overrides(model="offline", offline=True))
    traps = [r for r in rows if r.expected in ("rejected", "escalated", "duplicate_skipped")]
    escalated = sum(r.actual == "escalated" for r in rows) / len(rows)
    caught = sum(r.actual == r.expected for r in traps) / len(traps)
    return escalated, caught, len(rows)


esc, catch, n = measured_from_eval()
d = Assumptions()
top = st.container()  # the projection renders here, above the inputs that drive it
st.subheader("Inputs")
left, right = st.columns(2)
with left:
    st.markdown("**From the brief**")
    loss = st.number_input("Current annual cost of manual processing ($)", value=d.current_annual_loss, step=100_000.0)
    err = st.number_input("Current error rate", value=d.current_error_rate, step=0.05, format="%.2f")
    days = st.number_input("Current processing time (days)", value=d.current_cycle_days, step=0.5)
    st.markdown("**Measured**")
    cost = st.number_input(
        "Model cost per invoice ($)", value=0.046, step=0.01, format="%.3f",
        help="Live Grok 4.7 run over all 27 test invoices, at published API prices (docs/live).",
    )  # fmt: skip
    secs = st.number_input(
        "Processing time per invoice (s)", value=24.0, help="Live Grok run, 2026-11-13: 10.6 min / 27 invoices."
    )
    st.metric("Sent to a person (eval)", f"{esc:.0%}", help=f"Share of the {n} test invoices escalated to the inbox.")
    st.metric("Planted problems caught (eval)", f"{catch:.0%}")
with right:
    st.markdown("**Assumptions** (change these)")
    vol = st.number_input("Invoices per year · assumption", value=d.invoices_per_year, step=5_000)
    mins = st.number_input("Minutes per human review · assumption", value=d.review_minutes, step=5.0)
    rate = st.number_input("Loaded cost per AP hour ($) · assumption", value=d.loaded_hourly_cost, step=5.0)
    sla = st.number_input("Inbox turnaround (days) · assumption", value=d.review_turnaround_days, step=0.5)

a = Assumptions(int(vol), loss, err, days, mins, rate, sla)
p = project(a, Measured(esc, catch, cost, secs))
top.subheader("Projection")
c1, c2, c3, c4 = top.columns(4)
c1.metric("Annual cost", f"${p.total_cost:,.0f}", f"-${p.savings:,.0f} vs today", delta_color="inverse")
c2.metric("Handled with no person", f"{p.automated_share:.0%}")
c3.metric("Average cycle time", f"{p.cycle_days:.2f} days", f"{p.cycle_days - days:+.2f} days", delta_color="inverse")
c4.metric("Model spend per year", f"${p.model_cost:,.0f}")
top.caption(
    f"Annual cost = {vol:,} invoices x ${cost:.3f} model cost + {esc:.0%} reviewed x {mins:.0f} min x ${rate:.0f}/h. "
    f"Cycle time = automated share x {secs:.0f}s + reviewed share x {sla} day(s). "
    f"The error rate is not projected: the test set's planted problems were caught at {catch:.0%} against today's "
    f"{err:.0%} error rate, but {n} invoices are a test set weighted toward problems, so its {esc:.0%} escalation "
    "rate overstates what production would see."
)
