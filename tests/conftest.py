import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_agents.rules import Reference
from invoice_agents.seed import reset
from invoice_agents.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
INVOICES = ROOT / "data" / "invoices"


class Crash(BaseException):
    """The process dying: not an Exception, so the bank retry loop does not swallow it."""


def ok(vendor: str, amount: Decimal) -> dict[str, str]:
    return {"status": "success"}


def declined(vendor: str, amount: Decimal) -> dict[str, str]:
    return {"status": "declined"}


def recording_bank(outcome: dict[str, str] | BaseException):
    """A bank that answers ``outcome`` (or raises it) and records each amount it was asked to send."""
    calls: list[Decimal] = []

    def bank(vendor: str, amount: Decimal) -> dict[str, str]:
        calls.append(amount)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return bank, calls


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return reset(tmp_path / "t.db")


@pytest.fixture
def ref(conn: sqlite3.Connection) -> Reference:
    return Reference.load(conn)


@pytest.fixture
def offline(tmp_path: Path) -> Settings:
    return Settings(model="offline", offline=True, db_path=tmp_path / "t.db", runs_dir=tmp_path / "runs")
