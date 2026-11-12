"""Deterministic normalisation of the extractor's as-written strings into a typed :class:`Invoice`.

The LLM copies what the document says (``"$3,500.O0"``, ``"26-Jan-2O26"``,
``"Widget A"``); this module parses it. Keeping parsing in code makes it exact,
testable and identical across models.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field

from invoice_agents.models import FieldSource, Invoice, LineItem

SKUS = ("WidgetA", "WidgetB", "GadgetX", "FakeItem")
# US month-first for slashed dates (all samples are US vendors); ISO and month-name styles are unambiguous.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d %Y",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)
CURRENCY_SYMBOLS = {"€": "EUR", "£": "GBP", "$": "USD"}


class RawLine(BaseModel):
    """One line exactly as written on the document."""

    item: str
    quantity: str
    unit_price: str | None = None
    amount: str | None = None
    note: str | None = None


class RawExtraction(BaseModel):
    """The extractor's output: every value copied as written, or null if absent."""

    vendor: str | None = None
    vendor_address: str | None = None
    invoice_number: str | None = None
    revision: str | None = Field(default=None, description="Revision marker as written, e.g. 'R1'")
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = Field(default=None, description="ISO code if the document states one")
    lines: list[RawLine] = Field(default_factory=list[RawLine])
    subtotal: str | None = None
    tax: str | None = None
    shipping: str | None = None
    total: str | None = None
    payment_terms: str | None = None
    notes: str | None = None
    remit_to: str | None = None


class NormalizeError(ValueError):
    """A value could not be parsed."""


def ocr_digits(s: str) -> str:
    """Repair letter-for-digit OCR errors inside numeric tokens only (``2O26`` → ``2026``, ``O0`` → ``00``).

    A capital or lower-case O is replaced only when a digit sits on at least one
    side, so words like "Oct" or "SOLD" are untouched.
    """
    return re.sub(r"(?<=\d)[Oo]|[Oo](?=\d)", "0", s)


# Optional sign, optional currency symbol or code, then 1,234.56-style digits with an optional unit word ("12 pcs").
_AMOUNT = re.compile(
    r"^(?P<sign>[-+])?\s*(?:[$€£]|USD|EUR|GBP)?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?:USD|EUR|GBP|pcs|units?|ea(?:ch)?)?$",
    re.IGNORECASE,
)


def money(s: str | None) -> Decimal | None:
    """Parse an amount or quantity such as ``$1,500.00``, ``1500``, ``-250.00``, ``(250.00)`` or ``12 pcs``.

    Anything else (European ``1.234,56``, ``1,5``, ``1e5``, ``5%``) raises rather than
    guessing, so the extractor is asked again instead of a wrong number being paid.

    Raises:
        NormalizeError: The text is not an unambiguous amount.
    """
    if s is None or not s.strip():
        return None
    t = ocr_digits(s.strip())
    negative = t.startswith("(") and t.endswith(")")  # accounting notation for negatives
    if negative:
        t = t[1:-1].strip()
    m = _AMOUNT.match(t)
    if not m:
        raise NormalizeError(f"not an unambiguous amount: {s!r}")
    try:
        value = Decimal(m.group("num").replace(",", ""))
    except InvalidOperation as e:
        raise NormalizeError(f"not an amount: {s!r}") from e
    return -value if negative or m.group("sign") == "-" else value


def parse_date(s: str | None) -> date | None:
    """Parse the date styles seen on the sample invoices; None for blanks and relative words like 'yesterday'."""
    if s is None or not s.strip():
        return None
    t = re.sub(r"\s+", " ", ocr_digits(s.strip()))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def sku(item: str) -> str | None:
    """Canonical SKU for an item as written (``Widget A``, ``WidgetA (rush order)`` → ``WidgetA``)."""
    base = re.sub(r"\(.*?\)", "", item)
    key = re.sub(r"[^a-z0-9]", "", base.lower())
    return next((s for s in SKUS if s.lower() == key), None)


def invoice_number(s: str | None) -> str | None:
    """Canonical number: ``1002``, ``INV 1012`` and ``INV-1012`` all become ``INV-<digits>``."""
    if not s or not s.strip():
        return None
    m = re.fullmatch(r"(?:inv(?:oice)?)?[\s#:\-]*(\d+)", ocr_digits(s.strip()), re.IGNORECASE)
    return f"INV-{m.group(1)}" if m else (s.strip() if re.search(r"\d", s) else None)


def revision(s: str | None) -> int:
    """Revision number from a marker such as ``R1`` or ``Rev 2``; 0 if none."""
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else 0


def currency(raw: RawExtraction) -> str:
    """Stated ISO code, else inferred from currency symbols in the amounts, else USD."""
    code = (raw.currency or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    amounts = " ".join(x for x in (raw.total, raw.subtotal, *(ln.unit_price or "" for ln in raw.lines)) if x)
    return next((code for sym, code in CURRENCY_SYMBOLS.items() if sym in amounts), "USD")


def _quantity(s: str) -> Decimal:
    """A line quantity; a blank one is an extraction error, not zero."""
    q = money(s)
    if q is None:
        raise NormalizeError(f"line quantity is blank: {s!r}")
    return q


_FORMERLY = re.compile(r"\s*\((?:formerly|previously|f/k/a|fka)\s+([^)]+)\)\s*", re.IGNORECASE)


def vendor_name(s: str | None) -> str | None:
    """Vendor name without a '(formerly X)' note, so a rename does not change the ledger key."""
    return _blank(_FORMERLY.sub(" ", s or ""))


def former_name(s: str | None) -> str | None:
    """The former name from a '(formerly X)' note, if any."""
    m = _FORMERLY.search(s or "")
    return f"Formerly {m.group(1).strip()}" if m else None


def _join_notes(*parts: str | None) -> str | None:
    return _blank(" ".join(p for p in parts if p and p.strip()))


def _blank(s: str | None) -> str | None:
    return s.strip() if s and s.strip() else None


def to_invoice(raw: RawExtraction) -> Invoice:
    """Parse a raw extraction into a typed invoice, recording provenance per field.

    Raises:
        NormalizeError: A quantity or amount is not a number.
    """
    lines = [
        LineItem(
            item_raw=ln.item.strip(),
            sku=sku(ln.item),
            quantity=_quantity(ln.quantity),
            unit_price=money(ln.unit_price),
            amount=money(ln.amount),
            note=_blank(ln.note),
        )
        for ln in raw.lines
    ]
    due = parse_date(raw.due_date)
    inv = Invoice(
        vendor=vendor_name(raw.vendor),
        vendor_address=_blank(raw.vendor_address),
        invoice_number=invoice_number(raw.invoice_number),
        revision=revision(raw.revision),
        invoice_date=parse_date(raw.invoice_date),
        due_date=due,
        due_date_raw=_blank(raw.due_date) if due is None else None,
        currency=currency(raw),
        lines=lines,
        subtotal=money(raw.subtotal),
        tax=money(raw.tax),
        shipping=money(raw.shipping),
        total=money(raw.total),
        payment_terms=_blank(raw.payment_terms),
        notes=_join_notes(raw.notes, former_name(raw.vendor)),
        remit_to=_blank(raw.remit_to),
    )
    provenance: dict[str, FieldSource] = {
        k: ("llm" if getattr(raw, k) not in (None, "", []) else "missing") for k in RawExtraction.model_fields
    }
    return inv.model_copy(update={"provenance": provenance})
