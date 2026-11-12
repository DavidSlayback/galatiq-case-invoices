"""Rich rendering of outcomes for the terminal."""

import json
import sqlite3
from collections import Counter
from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from invoice_agents.models import Outcome, Status

STATUS_STYLE = {
    Status.PAID: "bold green",
    Status.REJECTED: "bold red",
    Status.ESCALATED: "bold yellow",
    Status.DUPLICATE_SKIPPED: "bold cyan",
    Status.SUPERSEDED: "bold cyan",
}
SEVERITY_STYLE = {"hard": "red", "fraud": "magenta", "soft": "yellow", "note": "dim"}


def outcome_panel(o: Outcome) -> Panel:
    """One invoice: header facts, findings, decision and reasons."""
    inv = o.invoice
    head = Table.grid(padding=(0, 2))
    head.add_row("Vendor", o.key.vendor, "Invoice", f"{o.key.invoice_number} r{o.key.revision}")
    if inv is not None:
        head.add_row("Total", f"{inv.total} {inv.currency}", "Due", str(inv.due_date or inv.due_date_raw or "-"))
    parts: list[Table | Text] = [head]
    if o.findings:
        ft = Table("Rule", "Severity", "Finding", box=None, pad_edge=False)
        for f in o.findings:
            ft.add_row(f.rule_id, Text(f.severity, style=SEVERITY_STYLE[f.severity]), f.message)
        parts.append(ft)
    else:
        parts.append(Text("No findings.", style="dim"))
    if o.decision:
        d = o.decision
        why = "; ".join(d.reasons) or "-"
        parts.append(Text.assemble(("Decision: ", "bold"), f"{d.kind} by {d.actor}. ", ("Why: ", "bold"), why))
    title = Text.assemble((o.status.value.upper(), STATUS_STYLE.get(o.status, "bold")), f"  {o.source_path or ''}")
    return Panel(Group(*parts), title=title, title_align="left")


def summary_table(outcomes: list[Outcome]) -> Table:
    """One row per processed file."""
    t = Table("File", "Invoice", "Vendor", "Total", "Status", "Decided by", "Flags", title="Batch summary")
    for o in outcomes:
        total = f"{o.invoice.total} {o.invoice.currency}" if o.invoice and o.invoice.total is not None else "-"
        flags = ", ".join(sorted({f.rule_id for f in o.findings if f.severity != "note"})) or "-"
        t.add_row(
            Path(o.source_path or "").name, o.key.invoice_number, o.key.vendor, total,
            Text(o.status.value, style=STATUS_STYLE.get(o.status, "")), o.decision.actor if o.decision else "-", flags,
        )  # fmt: skip
    counts = Counter(o.status.value for o in outcomes)
    t.caption = "  ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    return t


def history_table(rows: list[sqlite3.Row]) -> Table:
    """Event timeline for one invoice number."""
    t = Table("When (UTC)", "Rev", "Event", "Actor", "Details", title=f"History of {rows[0]['invoice_number']}")
    for r in rows:
        payload = json.loads(r["payload"])
        t.add_row(r["ts"][:19].replace("T", " "), str(r["revision"]), r["event"], r["actor"], _brief(payload))
    return t


def _brief(payload: dict[str, object]) -> str:
    keys = ("reason", "total_delta", "lines_added", "amount", "amount_due", "kind", "duplicate_of", "path")
    parts = [f"{k}={payload[k]}" for k in keys if payload.get(k) not in (None, [], "")]
    return "; ".join(parts)[:120]
