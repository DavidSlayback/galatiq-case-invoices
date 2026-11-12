"""Command-line interface (Typer)."""

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from invoice_agents import settings as settings_mod
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


def build_settings(
    model: str | None, offline: bool, as_of: str | None, db: Path | None
) -> settings_mod.Settings:
    """Merge environment settings with CLI overrides."""
    return settings_mod.from_env().with_overrides(
        model=model,
        offline=offline or None,
        as_of=date.fromisoformat(as_of) if as_of else None,
        db_path=db,
    )


def _not_yet() -> None:
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    invoice_path: Annotated[
        Path | None, typer.Option("--invoice_path", "--invoice-path", help="Process one invoice file.")
    ] = None,
    model: ModelOpt = None,
    offline: OfflineOpt = False,
    as_of: AsOfOpt = None,
    db: DbOpt = None,
) -> None:
    """Process invoices end to end. `--invoice_path` is the brief's entry point."""
    if ctx.invoked_subcommand is not None:
        return
    if invoice_path is None:
        console.print(ctx.get_help())
        raise typer.Exit(0)
    process(invoice_path, model=model, offline=offline, as_of=as_of, db=db)


@app.command()
def process(
    invoice_path: Path,
    model: ModelOpt = None,
    offline: OfflineOpt = False,
    as_of: AsOfOpt = None,
    db: DbOpt = None,
) -> None:
    """Run one invoice through ingestion, validation, approval and payment."""
    build_settings(model, offline, as_of, db)
    _not_yet()


@app.command("eval")
def eval_cmd(offline: OfflineOpt = False, model: ModelOpt = None) -> None:
    """Score every sample invoice against eval/expected_outcomes.yaml."""
    _not_yet()


@app.command()
def history(invoice_number: str) -> None:
    """Show the event timeline for one invoice."""
    _not_yet()


@app.command()
def review() -> None:
    """List and resolve escalated invoices."""
    _not_yet()


@app.command()
def reset(db: DbOpt = None) -> None:
    """Recreate and seed the database."""
    s = build_settings(None, False, None, db)
    reset_db(s.db_path).close()
    console.print(f"[green]Reset[/green] {s.db_path}: inventory, vendors and FX rates seeded.")


@app.command()
def ui() -> None:
    """Launch the Streamlit dashboard."""
    _not_yet()
