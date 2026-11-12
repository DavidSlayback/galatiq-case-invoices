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
DATE_FORMATS = ("%Y-%m-%d", "%b %d %Y", "%m/%d/%Y", "%d-%b-%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y")
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
    revision: str | None = Field(None, description="Revision marker as written, e.g. 'R1'")
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = Field(None, description="ISO code if the document states one")
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


def money(s: str | None) -> Decimal | None:
    """Parse an amount such as ``$1,500.00``, ``1500``, ``-250.00`` or ``€ 4.125,00``-free variants."""
    if s is None or not s.strip():
        return None
    t = ocr_digits(s)
    t = re.sub(r"[^\d.,\-]", "", t).replace(",", "")
    try:
        return Decimal(t)
    except InvalidOperation as e:
        raise NormalizeError(f"not an amount: {s!r}") from e


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
    return f"INV-{m.group(1)}" if m else s.strip()


def revision(s: str | None) -> int:
    """Revision number from a marker such as ``R1`` or ``Rev 2``; 0 if none."""
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else 0


def currency(raw: RawExtraction) -> str:
    """Stated ISO code, else inferred from currency symbols in the amounts, else USD."""
    if raw.currency and raw.currency.strip():
        return raw.currency.strip().upper()
    amounts = " ".join(x for x in (raw.total, raw.subtotal, *(ln.unit_price or "" for ln in raw.lines)) if x)
    return next((code for sym, code in CURRENCY_SYMBOLS.items() if sym in amounts), "USD")


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
            quantity=money(ln.quantity) or Decimal(0),
            unit_price=money(ln.unit_price),
            amount=money(ln.amount),
            note=_blank(ln.note),
        )
        for ln in raw.lines
    ]
    due = parse_date(raw.due_date)
    inv = Invoice(
        vendor=_blank(raw.vendor),
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
        notes=_blank(raw.notes),
        remit_to=_blank(raw.remit_to),
    )
    provenance: dict[str, FieldSource] = {
        k: ("llm" if getattr(raw, k) not in (None, "", []) else "missing") for k in RawExtraction.model_fields
    }
    return inv.model_copy(update={"provenance": provenance})
