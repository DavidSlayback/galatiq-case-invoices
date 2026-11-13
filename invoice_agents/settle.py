"""Settling a decided invoice: the one place an approval is paid or a rejection is logged (D4, D15, D19, D42).

The graph's final step and a person's inbox decision both end here, so the
guardrail, the audit events and the payment are identical whoever decided.
"""

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from invoice_agents import approval, db, payment
from invoice_agents.models import Decision, EventType, Finding, InvoiceKey, Status
from invoice_agents.payment import Bank, mock_payment


@dataclass(frozen=True)
class Settled:
    """What settling did: the final decision (after the guardrail), the status and any amount paid."""

    decision: Decision
    status: Status
    amount_paid: Decimal | None = None


def bad_lines(findings: list[Finding]) -> list[str]:
    """Items named by hard findings, so the vendor can reissue rather than be short-paid (D4)."""
    return sorted({str(f.evidence.get("item") or f.evidence.get("sku")) for f in findings
                   if f.severity == "hard" and (f.evidence.get("item") or f.evidence.get("sku"))})  # fmt: skip


def settle(
    conn: sqlite3.Connection,
    key: InvoiceKey,
    decision: Decision,
    *,
    findings: list[Finding],
    total: Decimal | None,
    currency: str,
    usd_total: Decimal | None,
    run_id: str,
    bank: Bank = mock_payment,
) -> Settled:
    """Apply the guardrail, record the decision, then pay or reject.

    Args:
        conn: Open connection.
        key: Ledger key of the invoice being settled.
        decision: An ``approve`` or ``reject`` decision, from rules, agents or a person.
        findings: The invoice's findings; any hard one turns an approval into a rejection (D15).
        total: Invoice total in its currency; required to approve.
        currency: Invoice currency.
        usd_total: Total in USD, recorded with the payment.
        run_id: Current run.
        bank: Payment API.

    Raises:
        ValueError: An approval with no total, or a decision that is neither approve nor reject.
    """
    final, overridden = approval.guard(decision, findings)
    if overridden:
        db.record(conn, key, EventType.GUARDRAIL_OVERRIDE, actor="guardrail", run_id=run_id,
                  payload={"proposed": decision.model_dump(), "final": final.model_dump()})  # fmt: skip
    if final.kind == "approve" and total is None:
        raise ValueError(f"cannot approve {key.invoice_number}: no total was extracted")
    if final.kind not in ("approve", "reject"):
        raise ValueError(f"settle takes approve or reject, not {final.kind}")
    db.record(conn, key, EventType.DECIDED, actor=final.actor, run_id=run_id, payload=final.model_dump())
    if final.kind == "reject":
        payload = {"reasons": final.reasons, "rule_ids": final.cited_rule_ids, "bad_lines": bad_lines(findings)}
        db.record(conn, key, EventType.REJECTED, actor=final.actor, run_id=run_id, payload=payload,
                  status=Status.REJECTED)  # fmt: skip
        return Settled(final, Status.REJECTED)
    assert total is not None
    res = payment.pay(conn, key, total, currency, usd_total, run_id, bank)
    return Settled(final, res.status, res.amount if res.status == Status.PAID else None)
