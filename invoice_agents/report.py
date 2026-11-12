"""Rich rendering of outcomes for the terminal."""

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
