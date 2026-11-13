"""Invoice identity: when two documents are the same invoice (D2, D36, D38).

Every ledger key is built here, and every key column in the database compares
through :func:`fold` (registered as the SQLite collation ``FOLD``). So
"WIDGETS  INC.", "widgets inc." and "Müller"/"MÜLLER" each name one vendor,
in Python and in SQL alike. A vendor named exactly or by a registry alias is
keyed under its registered name, so a resubmission under an alias meets the
original in the ledger (its differing name makes it a conflict, escalated as
fraud, never a silent new invoice). Forms equal only after NFKC (full-width
letters) share an identity by D36, so they can never be paid twice; the rules
still flag them as look-alikes. Edit-distance look-alikes ("Widgets lnc.") are
never resolved. A conflicting copy is recognised only here.
"""

import json
import sqlite3
import unicodedata

from invoice_agents.models import Invoice, InvoiceKey
from invoice_agents.normalize import invoice_number

COLLATION = "FOLD"
_CONFLICT = " (conflict "


def fold(s: str | None) -> str:
    """Comparison form: NFKC, full Unicode case folding, single spaces.

    NFKC makes full-width and compatibility forms one identity (D36), so a
    look-alike spelling can never open a second ledger row and be paid twice.
    It runs again after ``casefold``, whose output need not be NFKC-normal.
    """
    once = unicodedata.normalize("NFKC", s or "").casefold()
    return " ".join(unicodedata.normalize("NFKC", once).split())


def _collate(a: str, b: str) -> int:
    """SQLite collation callback: strings with the same :func:`fold` compare equal."""
    fa, fb = fold(a), fold(b)
    return (fa > fb) - (fa < fb)


def plain(s: str | None) -> str:
    """Case- and space-insensitive form *without* NFKC: tells a full-width look-alike from the real name."""
    return " ".join((s or "").casefold().split())


def register(conn: sqlite3.Connection) -> None:
    """Teach a connection the ``FOLD`` collation.

    Must run before any statement touches a key column; SQLite rejects such a
    statement ("no such collation sequence") on a connection without it.
    """
    conn.create_collation(COLLATION, _collate)


def registry(conn: sqlite3.Connection) -> dict[str, str]:
    """Folded registered name or alias → registered name.

    Raises:
        ValueError: One name or alias belongs to two vendors; paying either would be a guess.
    """
    out: dict[str, str] = {}
    for r in conn.execute("SELECT name, aliases_json FROM vendors ORDER BY name").fetchall():
        for n in (r["name"], *json.loads(r["aliases_json"])):
            if out.setdefault(fold(n), r["name"]) != r["name"]:
                raise ValueError(f"vendor registry: {n!r} names both {out[fold(n)]!r} and {r['name']!r}")
    return out


def key_for(conn: sqlite3.Connection, inv: Invoice, file_sha256: str) -> InvoiceKey:
    """Ledger key for an extracted invoice.

    The vendor is the registered name when the invoice names it exactly or by an
    alias, else the name as written (NFKC, spaces collapsed). Placeholders keep
    invoices with no vendor or number distinct from each other.

    Raises:
        ValueError: The vendor registry is ambiguous (see :func:`registry`).
    """
    written = " ".join(unicodedata.normalize("NFKC", inv.vendor or "").split())
    vendor = registry(conn).get(fold(written), written) if written else "(missing vendor)"
    number = (inv.invoice_number or "").strip() or f"(no number {file_sha256[:8]})"
    return InvoiceKey(vendor, number, inv.revision)


def conflict_key(key: InvoiceKey, file_sha256: str) -> InvoiceKey:
    """Key for a copy whose content conflicts with the invoice on file; the original's row stays intact.

    :func:`same_invoice` still matches the copy to the original, so anything
    paid on either counts against both (B7).
    """
    return key._replace(invoice_number=f"{key.invoice_number}{_CONFLICT}{file_sha256[:8]})")


def base_number(number: str) -> str:
    """The invoice number without a conflict copy's suffix."""
    return number.split(_CONFLICT)[0]


def same_invoice(a: str, b: str) -> bool:
    """Whether two invoice numbers name the same invoice, counting conflict copies (B7)."""
    return fold(base_number(a)) == fold(base_number(b))


def lookup_number(raw: str) -> str:
    """A number a person typed, in ledger form: ``inv 1012`` and ``1012`` find ``INV-1012``."""
    return invoice_number(raw) or raw.strip()
