"""Format loaders: turn an input file into a :class:`RawDocument`.

Loaders never interpret or execute content; they only read it.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

from invoice_agents.loaders import json_loader
from invoice_agents.models import RawDocument


class LoadError(Exception):
    """The file could not be read as a supported invoice document."""


Loader = Callable[[Path, bytes, str], RawDocument]

_LOADERS: dict[str, Loader] = {".json": json_loader.load}


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
        data = path.read_bytes()
    except OSError as e:
        raise LoadError(f"cannot read {path}: {e}") from e
    if not data.strip():
        raise LoadError(f"empty file: {path}")
    try:
        return loader(path, data, file_sha256(data))
    except LoadError:
        raise
    except Exception as e:  # any parser failure on untrusted input becomes a typed error
        raise LoadError(f"malformed {path.suffix} file {path.name}: {e}") from e
