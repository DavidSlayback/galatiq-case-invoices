from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from invoice_agents.cli import app, build_settings
from invoice_agents.settings import DEFAULT_AS_OF, from_env

runner = CliRunner()


def test_help_lists_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("process", "eval", "history", "review", "reset", "ui"):
        assert cmd in result.output


def test_invoice_path_alias_is_accepted():
    result = runner.invoke(app, ["--invoice_path=data/invoices/invoice_1001.txt"])
    assert "No such option" not in result.output


def test_env_defaults_and_overrides():
    s = from_env({})
    assert s.model is None and s.as_of == DEFAULT_AS_OF and s.db_path == Path("inventory.db")
    s = from_env({"INVOICE_MODEL": "offline", "INVOICE_AS_OF": "2026-03-01"})
    assert s.model == "offline" and s.as_of == date(2026, 3, 1)


def test_cli_overrides_beat_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INVOICE_MODEL", "cli:cursor:grok-4.7-low-fast")
    s = build_settings("offline", True, "2026-01-15", None)
    assert s.model == "offline" and s.offline and s.as_of == date(2026, 1, 15)
