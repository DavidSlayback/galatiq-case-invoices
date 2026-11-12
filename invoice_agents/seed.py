"""Seed data: the brief's inventory plus prices, the vendor registry and the mock FX table."""

import json
import sqlite3
from pathlib import Path

from invoice_agents.db import SCHEMA, connect

# The brief's stock levels; unit prices added so price checks have a catalog (D6).
INVENTORY = [
    ("WidgetA", 15, "250.00"),
    ("WidgetB", 10, "500.00"),
    ("GadgetX", 5, "750.00"),
    ("FakeItem", 0, "0.00"),
]

# Known vendors (D9). Fraudster LLC, NoProd Industries and Global Supply Chain
# Partners are deliberately absent. QuickShip is reachable only through the
# FastShip alias, so it raises a rename flag instead of passing as known.
VENDORS: list[tuple[str, str | None, list[str], str]] = [
    ("Widgets Inc.", "100 Main St, Chicago, IL 60601", [], "ACH-0001"),
    ("Gadgets Co.", None, [], "ACH-0002"),
    ("Precision Parts Ltd.", "742 Evergreen Terrace, Springfield, IL 62704", [], "ACH-0003"),
    ("Acme Industrial Supplies", None, [], "ACH-0004"),
    ("MegaWidgets Corp", None, [], "ACH-0005"),
    ("Consolidated Materials Group", None, [], "ACH-0006"),
    ("Summit Manufacturing Co.", None, [], "ACH-0007"),
    ("FastShip Ltd.", None, ["QuickShip Distributers", "QuickShip Distributors"], "ACH-0008"),
    ("Atlas Industrial Supply", "500 Commerce Blvd, Detroit, MI 48201", [], "ACH-0009"),
    ("TechParts International", None, [], "IBAN-DE-0010"),
    ("Reliable Components Inc.", None, [], "ACH-0011"),
]

# Mock rate, labelled as such (A6). No live FX at runtime (NFR-1).
FX_RATES = [("USD", "1", "2026-01-31", "identity"), ("EUR", "1.08", "2026-01-31", "mock")]


def seed(conn: sqlite3.Connection) -> None:
    """Insert seed rows, replacing any existing reference data."""
    with conn:
        conn.executemany("INSERT OR REPLACE INTO inventory VALUES (?, ?, ?)", INVENTORY)
        conn.executemany(
            "INSERT OR REPLACE INTO vendors VALUES (?, ?, 1, ?, ?)",
            [(n, a, json.dumps(al), b) for n, a, al, b in VENDORS],
        )
        conn.executemany("INSERT OR REPLACE INTO fx_rates VALUES (?, ?, ?, ?)", FX_RATES)


def open_db(path: Path) -> sqlite3.Connection:
    """Open the database, seeding it first if it does not exist yet."""
    if not path.exists():
        return reset(path)
    return connect(path)


def reset(path: Path) -> sqlite3.Connection:
    """Delete the database (and WAL files), recreate the schema and seed it."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    conn = connect(path)
    conn.executescript(SCHEMA)
    seed(conn)
    return conn
