"""Shared pieces for the Streamlit pages: settings, database, and rendering helpers."""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `streamlit run app/streamlit_app.py` does not put the repo on the path
    sys.path.insert(0, str(ROOT))

from invoice_agents import thread  # noqa: E402
from invoice_agents.agents.models import detect  # noqa: E402
from invoice_agents.models import Finding, Outcome  # noqa: E402
from invoice_agents.seed import open_db  # noqa: E402
from invoice_agents.settings import Settings, from_env  # noqa: E402

STATUS_COLOUR = {"paid": "green", "rejected": "red", "escalated": "orange", "duplicate_skipped": "blue"}
# The brief's samples, then follow-ups that show what changes after a person decides (data/followup).
SAMPLES = [p for d in ("invoices", "followup") for p in sorted((ROOT / "data" / d).rglob("*")) if p.is_file()]


def settings() -> Settings:
    """Settings from the environment plus the sidebar's model choice (kept in session state)."""
    base = from_env()
    if "model_choice" not in st.session_state:
        st.session_state.model_choice = "offline" if base.model in (None, "offline") else base.model
    with st.sidebar:
        st.markdown("### Model")
        auto, why = detect()
        options = ["offline", auto, "cli:cursor:grok-4.7-medium-fast", "cli:claude:haiku"]
        options = list(dict.fromkeys([st.session_state.model_choice, *options]))
        choice = st.selectbox("Backend", options, key="model_choice", help=f"Auto-detect would pick {auto}: {why}.")
        st.caption("Offline replays recorded answers; the others call a live model.")
        st.caption(f"Database: `{base.db_path}`  ·  as-of {base.as_of}")
    return base.with_overrides(model=choice, offline=choice == "offline")


def conn(s: Settings) -> sqlite3.Connection:
    """A connection for this script run (sqlite connections must not cross Streamlit threads)."""
    return open_db(s.db_path)


def chip(text: str, colour: str) -> str:
    """Inline coloured label using Streamlit's colour markdown."""
    return f":{colour}-badge[{text}]"


def findings_table(findings: list[Finding] | list[dict[str, Any]]) -> None:
    """Findings as a sortable table, hard first."""
    rows = [f.model_dump() if isinstance(f, Finding) else f for f in findings]
    order = {"hard": 0, "fraud": 1, "soft": 2, "note": 3}
    rows.sort(key=lambda r: order.get(r["severity"], 9))
    if not rows:
        st.success("No findings: every check passed.")
        return
    st.dataframe(
        [{"Rule": r["rule_id"], "Severity": r["severity"], "Finding": r["message"]} for r in rows],
        hide_index=True,
        width="stretch",
    )


def outcome_card(o: Outcome) -> None:
    """Decision summary: status, who decided, and why."""
    colour = STATUS_COLOUR.get(o.status.value, "gray")
    st.markdown(f"## {chip(o.status.value.replace('_', ' ').upper(), colour)}  {o.key.invoice_number} · {o.key.vendor}")
    inv = o.invoice
    cols = st.columns(4)
    cols[0].metric("Total", f"{inv.total} {inv.currency}" if inv and inv.total is not None else "-")
    cols[1].metric("Due", str(inv.due_date or inv.due_date_raw or "-") if inv else "-")
    cols[2].metric("Decided by", o.decision.actor if o.decision else "-")
    cols[3].metric("Paid", str(o.amount_paid) if o.amount_paid is not None else "-")
    if o.decision and o.decision.reasons:
        label = f" ({o.decision.label})" if o.decision.label else ""
        head, *rest = o.decision.reasons
        st.info(f"**Why{label}:** {head.replace('_', ' ')}" + "".join(f"\n\n{x}" for x in rest))


def trace(s: Settings, run_id: str) -> list[dict[str, Any]]:
    """The JSONL trace lines for one run."""
    p = s.runs_dir / f"{run_id}.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


SPEAKERS = {
    "extractor": ("Extraction agent", ":material/document_scanner:"),
    "code": ("Rules and ledger (code)", ":material/rule:"),
    "vp": ("VP agent", ":material/gavel:"),
    "critic": ("Critic agent", ":material/fact_check:"),
}


def conversation(lines: list[dict[str, Any]]) -> None:
    """Show a run's trace as the conversation between the agents and the code (D51)."""
    for turn in thread.turns(lines):
        name, avatar = SPEAKERS[turn.speaker]
        with st.chat_message(turn.speaker, avatar=avatar):
            st.markdown(f"**{name}** · {turn.text}")
            for d in turn.details:
                st.markdown(f"- {d}")
