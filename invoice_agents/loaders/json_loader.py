"""JSON invoices: parsed fields plus the original text for the extractor."""

import json
from pathlib import Path

from invoice_agents.models import RawDocument


def load(path: Path, data: bytes, sha: str) -> RawDocument:
    """Parse a JSON invoice; the text passed on is the file's own text."""
    text = data.decode("utf-8")
    fields = json.loads(text)
    if not isinstance(fields, dict):
        raise ValueError("top-level JSON value is not an object")
    return RawDocument(path=str(path), file_sha256=sha, format="json", text=text, fields=fields)
