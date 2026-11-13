"""Domain types shared by every stage.

Money and quantities are ``Decimal`` so arithmetic checks are exact.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

FieldSource = Literal["parsed", "llm", "missing"]
Severity = Literal["hard", "soft", "fraud", "note"]
DocFormat = Literal["json", "csv", "xml", "txt", "pdf"]


class RawDocument(BaseModel):
    """A loaded input file before extraction.

    Attributes:
        path: Source path as given.
        file_sha256: Hash of the file bytes; keys offline golden fixtures.
        format: Detected format.
        text: Human-readable text of the document, as passed to the extractor.
        fields: Values a deterministic parser read directly (format-specific keys).
        page_images: PNG bytes of pages that had no text layer (scanned PDFs).
    """

    model_config = ConfigDict(frozen=True)

    path: str
    file_sha256: str
    format: DocFormat
    text: str
    fields: dict[str, Any] = Field(default_factory=dict)
    page_images: list[bytes] = Field(default_factory=list)


class LineItem(BaseModel):
    """One invoice line.

    Attributes:
        item_raw: Item text exactly as written on the invoice.
        sku: Canonical inventory SKU, or None if it could not be mapped.
        quantity: Quantity; may be negative on malformed invoices.
        unit_price: Price per unit in the invoice currency.
        amount: Line total as stated on the invoice, if stated.
        note: Line annotation such as "Volume discount".
    """

    item_raw: str
    sku: str | None = None
    quantity: Decimal
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    note: str | None = None


class Invoice(BaseModel):
    """Structured invoice produced by the extraction agent.

    Stated values are kept as written, even when inconsistent; validation
    rules decide what is wrong. ``provenance`` maps field names to how the
    value was obtained.
    """

    vendor: str | None = None
    vendor_address: str | None = None
    invoice_number: str | None = None
    revision: int = 0
    invoice_date: date | None = None
    due_date: date | None = None
    due_date_raw: str | None = None
    currency: str = "USD"
    lines: list[LineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    shipping: Decimal | None = None
    total: Decimal | None = None
    payment_terms: str | None = None
    notes: str | None = None
    remit_to: str | None = None
    provenance: dict[str, FieldSource] = Field(default_factory=dict)


class Finding(BaseModel):
    """A rule result. ``rule_id`` is stable and cited by agents and the eval."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    severity: Severity
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    """An approval decision and who made it."""

    kind: Literal["approve", "reject", "escalate"]
    actor: str
    reasons: list[str] = Field(default_factory=list)
    cited_rule_ids: list[str] = Field(default_factory=list)
    label: str | None = None


class Status(StrEnum):
    """Current status of an invoice in the ledger."""

    RECEIVED = "received"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    DUPLICATE_SKIPPED = "duplicate_skipped"


class EventType(StrEnum):
    """Business events appended to ``invoice_events`` (D25, D25a)."""

    RECEIVED = "received"
    EXTRACTED = "extracted"
    DUPLICATE_SKIPPED = "duplicate_skipped"
    SUPERSEDED = "superseded"
    VALIDATED = "validated"
    DECIDED = "decided"
    GUARDRAIL_OVERRIDE = "guardrail_override"
    ESCALATED = "escalated"
    WITHDRAWN = "withdrawn"
    HUMAN_DECISION = "human_decision"
    PAID = "paid"
    PAYMENT_SKIPPED_ALREADY_PAID = "payment_skipped_already_paid"
    PAYMENT_FAILED = "payment_failed"
    REVISION_AFTER_PAYMENT = "revision_after_payment"
    REJECTED = "rejected"
    VENDOR_MASTER_UPDATED = "vendor_master_updated"


class InvoiceKey(NamedTuple):
    """Ledger identity: vendor + invoice number, with the revision carried alongside (D2)."""

    vendor: str
    invoice_number: str
    revision: int = 0


class Outcome(BaseModel):
    """Final result of processing one file."""

    key: InvoiceKey
    status: Status
    decision: Decision | None = None
    findings: list[Finding] = Field(default_factory=list)
    run_id: str
    invoice: Invoice | None = None
    amount_paid: Decimal | None = None
    source_path: str | None = None
