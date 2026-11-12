"""JSON invoices: parsed fields plus the original text for the extractor."""

import json
from pathlib import Path

from invoice_agents.models import RawDocument


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard JSON constant {name}")


def load(path: Path, data: bytes, sha: str) -> RawDocument:
    """Parse a JSON invoice; the text passed on is the file's own text."""
    text = data.decode("utf-8-sig")
    fields = json.loads(text, parse_constant=_reject_constant)
    if not isinstance(fields, dict):
        raise ValueError("top-level JSON value is not an object")
    return RawDocument(path=str(path), file_sha256=sha, format="json", text=text, fields=fields)
