"""Fill or check ``file_sha256`` in golden fixtures from each golden's ``source`` file.

Usage: uv run python scripts/stamp_goldens.py [--check]
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Stamp every golden; with --check, report stale ones and exit 1 instead."""
    check = "--check" in sys.argv
    stale = 0
    for p in sorted((ROOT / "fixtures" / "golden").rglob("*.json")):
        g = json.loads(p.read_text(encoding="utf-8"))
        sha = hashlib.sha256((ROOT / g["source"]).read_bytes()).hexdigest()
        if g.get("file_sha256") != sha:
            stale += 1
            if check:
                print(f"stale: {p.relative_to(ROOT)}")
            else:
                g = {
                    "source": g["source"],
                    "file_sha256": sha,
                    **{k: v for k, v in g.items() if k not in ("source", "file_sha256")},
                }
                p.write_text(json.dumps(g, indent=2) + "\n", encoding="utf-8")
                print(f"stamped: {p.relative_to(ROOT)}")
    return 1 if check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
