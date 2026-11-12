"""Approval routing (D7), review-loop states and the guardrail (D15, FR-3.6).

``route`` and ``guard`` are pure; the graph runs the agents between them.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from invoice_agents.models import Decision, Finding, Invoice

AUTO_LIMIT = Decimal("10000")
HUMAN_ABOVE = Decimal("50000")
MAX_REVIEW_ROUNDS = 2
FRAUD_LABEL = "suspected fraud"


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


@dataclass(frozen=True)
class Proposed(Routed):
    """The VP's proposal for this round, awaiting the critic."""

    decision: Decision | None = None
    round: int = 0


@dataclass(frozen=True)
class Objected(Routed):
    """The critic objected; the VP gets another round."""

    objections: tuple[str, ...] = ()
    round: int = 0


Route = AutoApprove | VpReview | HumanReview | Reject


def _ids(findings: list[Finding], *severities: str) -> list[str]:
    return [f.rule_id for f in findings if f.severity in severities]


def route(invoice: Invoice, findings: list[Finding], usd_total: Decimal | None) -> Route:
    """Pick the approval path for a validated invoice (D7, D10, D27).

    Order matters: hard findings reject first, so a fraud signal on an invoice
    that is invalid anyway does not cost a human's time.
    """
    hard = _ids(findings, "hard")
    if hard:
        reasons = [f.message for f in findings if f.severity == "hard"]
        return Reject(
            invoice,
            findings,
            usd_total,
            decision=Decision(kind="reject", actor="rules", reasons=reasons, cited_rule_ids=hard),
        )
    fraud = _ids(findings, "fraud")
    if fraud:
        return HumanReview(invoice, findings, usd_total, reason="fraud signals: " + ", ".join(fraud), label=FRAUD_LABEL)
    if usd_total is None:
        return HumanReview(invoice, findings, usd_total, reason="total could not be determined in USD")
    if usd_total > HUMAN_ABOVE:
        return HumanReview(invoice, findings, usd_total, reason=f"total {usd_total} USD exceeds {HUMAN_ABOVE}")
    if usd_total >= AUTO_LIMIT or _ids(findings, "soft"):
        return VpReview(invoice, findings, usd_total)
    return AutoApprove(invoice, findings, usd_total)


def guard(decision: Decision, findings: list[Finding]) -> tuple[Decision, bool]:
    """Coerce an approval to a rejection when any hard finding exists (FR-3.6).

    Returns:
        The decision to act on, and whether the guardrail overrode the reviewer.
    """
    hard = _ids(findings, "hard")
    if decision.kind == "approve" and hard:
        return (
            Decision(
                kind="reject", actor="guardrail", cited_rule_ids=hard,
                reasons=[f"approval blocked: hard findings {', '.join(hard)}", *decision.reasons],
            ),
            True,
        )  # fmt: skip
    return decision, False
