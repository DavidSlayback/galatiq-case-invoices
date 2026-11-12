"""Command-line interface (Typer)."""

import contextlib
import io
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from invoice_agents import eval as eval_mod
from invoice_agents import graph, inbox
from invoice_agents import settings as settings_mod
from invoice_agents.agents.cli_bridge import BackendQuotaError
from invoice_agents.agents.models import detect
from invoice_agents.agents.offline import MissingFixture
from invoice_agents.report import history_table, inbox_table, outcome_panel, summary_table
from invoice_agents.seed import open_db
from invoice_agents.seed import reset as reset_db

app = typer.Typer(no_args_is_help=False, add_completion=False, help="Acme invoice processing agents.")
console = Console()

ModelOpt = Annotated[
    str | None,
    typer.Option("--model", help="Model spec: offline, a PydanticAI model string, or cli:<tool>:<model>."),
]
OfflineOpt = Annotated[bool, typer.Option("--offline", help="Replay golden model outputs; no network.")]
AsOfOpt = Annotated[str | None, typer.Option("--as-of", help="Processing date (YYYY-MM-DD) for date rules.")]
DbOpt = Annotated[Path | None, typer.Option("--db", help="SQLite database path.")]


def build_settings(model: str | None, offline: bool, as_of: str | None, db: Path | None) -> settings_mod.Settings:
    """Merge environment settings with CLI overrides."""
    return settings_mod.from_env().with_overrides(
        model=model,
        offline=offline or None,
        as_of=date.fromisoformat(as_of) if as_of else None,
        db_path=db,
    )


def with_backend(s: settings_mod.Settings) -> settings_mod.Settings:
    """Resolve an unset model with auto-detect (D32) and say which backend runs and why."""
    if s.offline or s.model:
        console.print(f"[dim]Model: {'offline replay' if s.offline else s.model} (configured)[/dim]")
        return s
    spec, why = detect()
    console.print(f"[dim]Model: {spec} ({why}). Override with --model or INVOICE_MODEL.[/dim]")
    return s.with_overrides(model=spec, offline=True if spec == "offline" else None)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    invoice_path: Annotated[
        Path | None, typer.Option("--invoice_path", "--invoice-path", help="Process one invoice file.")
    ] = None,
    invoice_dir: Annotated[
        Path | None, typer.Option("--invoice_dir", "--invoice-dir", help="Process every file in a directory.")
    ] = None,
    model: ModelOpt = None,
    offline: OfflineOpt = False,
    as_of: AsOfOpt = None,
    db: DbOpt = None,
) -> None:
    """Process invoices end to end. `--invoice_path` is the brief's entry point."""
    if ctx.invoked_subcommand is not None:
        return
    if invoice_dir is not None:
        batch(invoice_dir, model=model, offline=offline, as_of=as_of, db=db)
    elif invoice_path is not None:
        process(invoice_path, model=model, offline=offline, as_of=as_of, db=db)
    else:
        console.print(ctx.get_help())
        raise typer.Exit(0)


@app.command()
def process(
    invoice_path: Path,
    model: ModelOpt = None,
    offline: OfflineOpt = False,
    as_of: AsOfOpt = None,
    db: DbOpt = None,
) -> None:
    """Run one invoice through ingestion, validation, approval and payment."""
    s = with_backend(build_settings(model, offline, as_of, db))
    conn = open_db(s.db_path)
    try:
        outcome = graph.process_sync(invoice_path, s, conn)
    except MissingFixture as e:
        console.print(f"[red]Offline mode has no recorded answer for this file:[/red] {e}")
        raise typer.Exit(2) from e
    except BackendQuotaError as e:
        console.print(f"[red]Stopped: {e}[/red] Wait for the quota to reset or pick another --model.")
        raise typer.Exit(3) from e
    console.print(outcome_panel(outcome))


@app.command("eval")
def eval_cmd(
    offline: OfflineOpt = False,
    model: ModelOpt = None,
    scorecard: Annotated[
        Path | None, typer.Option(help="Write the Markdown scorecard here (offline default: docs/scorecard.md).")
    ] = None,
    record: Annotated[
        Path | None, typer.Option(help="With a live model, save each extraction here to compare with the goldens.")
    ] = None,
) -> None:
    """Score every sample invoice against eval/expected_outcomes.yaml (fresh database, fixed order)."""
    s = with_backend(build_settings(model, offline, None, None))
    try:
        rows = eval_mod.run(s, record_dir=record)
    except BackendQuotaError as e:
        console.print(f"[red]Stopped: {e}[/red] Wait for the quota to reset or pick another --model.")
        raise typer.Exit(3) from e
    console.print(eval_mod.table(rows))
    if scorecard is None and s.offline:  # a live eval must not overwrite the offline scorecard
        scorecard = Path("docs/scorecard.md")
    if scorecard:
        scorecard.write_text(eval_mod.markdown(rows, s.model or "offline"), encoding="utf-8")
    bad = eval_mod.failures(rows)
    console.print(f"{sum(r.passed for r in rows)}/{len(rows)} pass, {len(bad)} failing.")
    raise typer.Exit(1 if bad else 0)


@app.command()
def history(invoice_number: str, db: DbOpt = None) -> None:
    """Show the event timeline for one invoice (every vendor and revision with that number)."""
    s = build_settings(None, False, None, db)
    conn = open_db(s.db_path)
    rows = conn.execute("SELECT * FROM invoice_events WHERE invoice_number=? ORDER BY id", (invoice_number,)).fetchall()
    if not rows:
        console.print(f"[yellow]No events for {invoice_number}.[/yellow]")
        raise typer.Exit(1)
    console.print(history_table(rows))


@app.command()
def batch(
    invoice_dir: Path,
    model: ModelOpt = None,
    offline: OfflineOpt = False,
    as_of: AsOfOpt = None,
    db: DbOpt = None,
) -> None:
    """Process every file in a directory, in name order, and print a summary."""
    s = with_backend(build_settings(model, offline, as_of, db))
    conn = open_db(s.db_path)
    outcomes = []
    for path in sorted(p for p in invoice_dir.rglob("*") if p.is_file()):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                outcomes.append(graph.process_sync(path, s, conn))
        except MissingFixture as e:
            console.print(f"[red]skipped {path.name}:[/red] {e}")
        except BackendQuotaError as e:
            console.print(f"[red]Stopped: {e}[/red]")
            raise typer.Exit(3) from e
    console.print(summary_table(outcomes, s.runs_dir, s.model))


@app.command()
def review(
    invoice_number: Annotated[str | None, typer.Argument(help="Invoice to resolve; omit to list the inbox.")] = None,
    approve: Annotated[bool, typer.Option("--approve", help="Approve and pay.")] = False,
    reject: Annotated[bool, typer.Option("--reject", help="Reject.")] = False,
    note: Annotated[str, typer.Option("--note", help="Required reason for the decision.")] = "",
    vendor: Annotated[str | None, typer.Option("--vendor", help="Needed when two vendors share the number.")] = None,
    db: DbOpt = None,
) -> None:
    """List escalated invoices, or approve/reject one with a note."""
    conn = open_db(build_settings(None, False, None, db).db_path)
    if invoice_number is None:
        console.print(inbox_table(inbox.list_open(conn)))
        return
    if approve == reject:
        console.print("[red]Choose exactly one of --approve or --reject.[/red]")
        raise typer.Exit(2)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = inbox.resolve(
                conn, invoice_number, approve=approve, note=note, reviewer="human:cli", vendor=vendor
            )
    except inbox.InboxError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    console.print(f"[green]{invoice_number}: {result['status']}[/green] {result.get('amount', '')}")


@app.command()
def reset(db: DbOpt = None) -> None:
    """Recreate and seed the database."""
    s = build_settings(None, False, None, db)
    reset_db(s.db_path).close()
    console.print(f"[green]Reset[/green] {s.db_path}: inventory, vendors and FX rates seeded.")


@app.command()
def ui() -> None:
    """Launch the Streamlit dashboard."""
    app_path = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)]))
