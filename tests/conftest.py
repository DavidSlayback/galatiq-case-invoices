import sqlite3
from pathlib import Path

import pytest

from invoice_agents.seed import reset
from invoice_agents.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
INVOICES = ROOT / "data" / "invoices"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return reset(tmp_path / "t.db")


@pytest.fixture
def offline(tmp_path: Path) -> Settings:
    return Settings(model="offline", offline=True, db_path=tmp_path / "t.db", runs_dir=tmp_path / "runs")
