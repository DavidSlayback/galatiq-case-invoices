"""Ledger identity for invoices (D2)."""

from invoice_agents.models import Invoice, InvoiceKey


def key_for(inv: Invoice, file_sha256: str) -> InvoiceKey:
    """Ledger key for an extracted invoice; placeholders keep unidentifiable invoices distinct."""
    vendor = (inv.vendor or "").strip() or "(missing vendor)"
    number = (inv.invoice_number or "").strip() or f"(no number {file_sha256[:8]})"
    return InvoiceKey(vendor, number, inv.revision)
