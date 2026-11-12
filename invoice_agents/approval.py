"""Approval routing (D7). Pure: findings and amount in, route out."""

from dataclasses import dataclass, field
from decimal import Decimal

from invoice_agents.models import Decision, Finding, Invoice

AUTO_LIMIT = Decimal("10000")


@dataclass(frozen=True)
class Routed:
    """An invoice plus its findings, on its way to a decision."""

    invoice: Invoice
    findings: list[Finding] = field(default_factory=list[Finding])
    usd_total: Decimal | None = None


@dataclass(frozen=True)
class AutoApprove(Routed):
    """Clean and under the auto-approval limit."""


@dataclass(frozen=True)
class VpReview(Routed):
    """Needs the VP agent's judgement."""


@dataclass(frozen=True)
class HumanReview(Routed):
    """Goes to the human inbox."""

    reason: str = ""
    label: str | None = None


@dataclass(frozen=True)
class Reject(Routed):
    """Rejected; ``decision`` records who decided and why."""

    decision: Decision | None = None


@dataclass(frozen=True)
class Approve(Routed):
    """Approved after review; ``decision`` records who decided and why."""

    decision: Decision | None = None


Route = AutoApprove | VpReview | HumanReview | Reject


def route(invoice: Invoice, findings: list[Finding], usd_total: Decimal | None) -> Route:
    """Pick the approval path for a validated invoice.

    Hard findings reject before anything else. Anything else that is not clean
    and under the limit goes to a reviewer.
    """
    hard = [f.rule_id for f in findings if f.severity == "hard"]
    if hard:
        decision = Decision(
            kind="reject",
            actor="rules",
            reasons=[f.message for f in findings if f.severity == "hard"],
            cited_rule_ids=hard,
        )
        return Reject(invoice, findings, usd_total, decision=decision)
    flagged = [f for f in findings if f.severity in ("soft", "fraud")]
    if usd_total is not None and usd_total < AUTO_LIMIT and not flagged:
        return AutoApprove(invoice, findings, usd_total)
    return HumanReview(invoice, findings, usd_total, reason="needs review")
