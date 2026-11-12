"""Runtime settings, read from the environment and overridden by CLI flags."""

import os
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

# The sample invoices are dated Jan-Feb 2026; checking them against the real
# date would make every one past due (D8).
DEFAULT_AS_OF = date(2026, 2, 1)


@dataclass(frozen=True)
class Settings:
    """Immutable run configuration.

    Attributes:
        model: Model spec (``offline``, a PydanticAI model string, or ``cli:<tool>:<model>``).
            ``None`` means auto-detect (D32).
        db_path: SQLite database holding inventory, vendors, the ledger and events.
        as_of: Processing date used by date rules.
        offline: Replay golden model outputs instead of calling a model.
        runs_dir: Directory for per-run JSONL agent traces.
    """

    model: str | None = None
    db_path: Path = Path("inventory.db")
    as_of: date = DEFAULT_AS_OF
    offline: bool = False
    runs_dir: Path = Path("runs")

    def with_overrides(self, **changes: object) -> Settings:
        """Return a copy with every non-None override applied."""
        return replace(self, **{k: v for k, v in changes.items() if v is not None})  # pyright: ignore[reportArgumentType]


def from_env(env: dict[str, str] | None = None) -> Settings:
    """Build settings from environment variables.

    Args:
        env: Mapping to read instead of ``os.environ`` (for tests).

    Returns:
        Settings with ``INVOICE_MODEL``, ``INVOICE_DB``, ``INVOICE_AS_OF`` and ``RUNS_DIR`` applied.
    """
    e = os.environ if env is None else env
    as_of = e.get("INVOICE_AS_OF")
    return Settings(
        model=e.get("INVOICE_MODEL") or None,
        db_path=Path(e.get("INVOICE_DB", "inventory.db")),
        as_of=date.fromisoformat(as_of) if as_of else DEFAULT_AS_OF,
        runs_dir=Path(e.get("RUNS_DIR", "runs")),
    )
