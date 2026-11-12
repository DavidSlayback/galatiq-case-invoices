"""Format loaders: turn an input file into a :class:`RawDocument`.

Loaders never interpret or execute content; they only read it.
"""

import hashlib
import stat
from collections.abc import Callable
from pathlib import Path

from invoice_agents.loaders import json_loader, text_loaders
from invoice_agents.models import RawDocument

MAX_BYTES = 20 * 1024 * 1024


class LoadError(Exception):
    """The file could not be read as a supported invoice document."""


Loader = Callable[[Path, bytes, str], RawDocument]

_LOADERS: dict[str, Loader] = {
    ".json": json_loader.load,
    ".txt": text_loaders.load_txt,
    ".eml": text_loaders.load_txt,
    ".csv": text_loaders.load_csv,
    ".xml": text_loaders.load_xml,
    ".pdf": text_loaders.load_pdf,
}


def file_sha256(data: bytes) -> str:
    """Hex SHA-256 of file bytes."""
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> RawDocument:
    """Load one invoice file.

    Args:
        path: File to read.

    Returns:
        The loaded document.

    Raises:
        LoadError: Missing, empty, unsupported or malformed file.
    """
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        raise LoadError(f"unsupported file type: {path.suffix or '(none)'}")
    try:
        st = path.stat()
    except OSError as e:
        raise LoadError(f"cannot read {path}: {e}") from e
    # Only regular files: a FIFO or device with an invoice suffix would block or stream forever.
    if not stat.S_ISREG(st.st_mode):
        raise LoadError(f"not a regular file: {path}")
    if st.st_size > MAX_BYTES:
        raise LoadError(f"file too large ({st.st_size} bytes; limit {MAX_BYTES})")
    try:
        data = path.read_bytes()
    except OSError as e:
        raise LoadError(f"cannot read {path}: {e}") from e
    if not data.strip():
        raise LoadError(f"empty file: {path}")
    try:
        doc = loader(path, data, file_sha256(data))
    except LoadError:
        raise
    except Exception as e:  # any parser failure on untrusted input becomes a typed error
        raise LoadError(f"malformed {path.suffix} file {path.name}: {e}") from e
    if not doc.text.strip() and not doc.page_images:
        raise LoadError(f"no readable content in {path.name}")
    return doc
