"""Process one invoice and watch each stage."""

import contextlib
import io
from pathlib import Path

import streamlit as st

from app.common import ROOT, SAMPLES, conn, conversation, findings_table, outcome_card, settings, trace
from invoice_agents import graph
from invoice_agents.agents.offline import MissingFixture

STAGE_LABELS = {
    "load": "Read the file",
    "extract": "Extraction agent",
    "reconcile": "Check the arithmetic",
    "ledger": "Duplicate and revision check",
    "route": "Rules and routing",
    "vp_propose": "VP agent proposes",
    "critique": "Critic reviews",
}

s = settings()
st.title("Process an invoice")
st.caption(
    "Extraction → arithmetic self-check → duplicate check → rules → VP and critic review → payment or inbox. "
    "Every step is logged to the event ledger."
)

left, right = st.columns([2, 1])
with left:
    names = [str(p.relative_to(ROOT / "data")) for p in SAMPLES]
    sample = st.selectbox(
        "Sample invoice",
        names,
        key="sample",
        index=names.index("invoices/invoice_1012.txt") if "invoices/invoice_1012.txt" in names else 0,
    )
with right:
    upload = st.file_uploader("…or upload one", type=["pdf", "txt", "json", "csv", "xml"])

if st.button("Process", type="primary"):
    if upload is not None:
        dest = s.runs_dir / "uploads" / Path(upload.name).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(upload.getvalue())
        path = dest
    else:
        path = ROOT / "data" / sample
    with st.status(f"Processing {path.name}…", expanded=True) as status:
        try:
            with contextlib.redirect_stdout(io.StringIO()):  # mock_payment prints to the server console
                st.session_state.outcome = graph.process_sync(path, s, conn(s))
            status.update(label=f"Done: {path.name}", state="complete")
        except MissingFixture as e:
            status.update(label="No recorded answer for this file in offline mode", state="error")
            st.error(f"{e}. Pick a live backend in the sidebar to process new files.")
            st.session_state.pop("outcome", None)

o = st.session_state.get("outcome")
if o is not None:
    outcome_card(o)
    st.subheader("Findings")
    findings_table(o.findings)
    st.subheader("How the agents decided")
    lines = trace(s, o.run_id)
    conversation(lines)
    with st.expander("Raw trace (every stage, with timings and tokens)"):
        for t in lines:
            label = STAGE_LABELS.get(t["node"], t["node"])
            st.markdown(f"`{t['t']:.2f}s` · {label}" + (f" · round {t['round']}" if "round" in t else ""))
            st.json({k: v for k, v in t.items() if k not in ("run_id", "node", "t")}, expanded=False)
    if o.status.value == "escalated":
        st.warning("This invoice is waiting for a person. Open **Review inbox** in the sidebar to resolve it.")
