"""Invoice identity: when two documents are the same invoice (D2, D36, D38).

Every ledger key is built here, and every key column in the database compares
through :func:`fold` (registered as the SQLite collation ``FOLD``). So
"WIDGETS  INC.", "widgets inc." and "Müller"/"MÜLLER" each name one vendor,
in Python and in SQL alike. A vendor named exactly or by a registry alias is
keyed under its registered name, so a resubmission under an alias still meets
the original in the ledger; a look-alike is never resolved (it must not
inherit a real vendor's history). A conflicting copy is recognised only here.
"""

import json
import sqlite3
import unicodedata

from invoice_agents.models import Invoice, InvoiceKey
from invoice_agents.normalize import invoice_number

COLLATION = "FOLD"
_CONFLICT = " (conflict "


def fold(s: str | None) -> str:
    """Comparison form: NFKC, full Unicode case folding, single spaces."""
    once = unicodedata.normalize("NFKC", s or "").casefold()
    return " ".join(unicodedata.normalize("NFKC", once).split())


def _collate(a: str, b: str) -> int:
    fa, fb = fold(a), fold(b)
    return (fa > fb) - (fa < fb)


def register(conn: sqlite3.Connection) -> None:
    """Teach a connection the ``FOLD`` collation (must run before the schema is used)."""
    conn.create_collation(COLLATION, _collate)


def registry(conn: sqlite3.Connection) -> dict[str, str]:
    """Folded registered name or alias → registered name."""
    out: dict[str, str] = {}
    for r in conn.execute("SELECT name, aliases_json FROM vendors").fetchall():
        out[fold(r["name"])] = r["name"]
        for a in json.loads(r["aliases_json"]):
            out.setdefault(fold(a), r["name"])
    return out


def key_for(conn: sqlite3.Connection, inv: Invoice, file_sha256: str) -> InvoiceKey:
    """Ledger key for an extracted invoice.

    The vendor is the registered name when the invoice names it exactly or by an
    alias, else the name as written (spaces collapsed). Placeholders keep
    invoices with no vendor or number distinct from each other.
    """
    written = " ".join(unicodedata.normalize("NFKC", inv.vendor or "").split())
    vendor = registry(conn).get(fold(written), written) if written else "(missing vendor)"
    number = (inv.invoice_number or "").strip() or f"(no number {file_sha256[:8]})"
    return InvoiceKey(vendor, number, inv.revision)


def conflict_key(key: InvoiceKey, file_sha256: str) -> InvoiceKey:
    """Key for a copy whose content conflicts with the invoice on file; the original's row stays intact."""
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
