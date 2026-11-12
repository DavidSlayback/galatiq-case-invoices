"""Per-run JSONL trace of graph nodes and agent calls (D17)."""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def new_run_id() -> str:
    """Short sortable run id."""
    return time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


@dataclass
class Tracer:
    """Appends one JSON object per line to ``<runs_dir>/<run_id>.jsonl``."""

    runs_dir: Path
    run_id: str
    _t0: float = field(default_factory=time.perf_counter)

    @property
    def path(self) -> Path:
        """Trace file path."""
        return self.runs_dir / f"{self.run_id}.jsonl"

    def log(self, node: str, **data: Any) -> None:
        """Write one trace line with elapsed seconds since the run started."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        line = {"run_id": self.run_id, "node": node, "t": round(time.perf_counter() - self._t0, 4), **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
