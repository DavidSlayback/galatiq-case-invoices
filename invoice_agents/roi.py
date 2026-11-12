"""Business-impact projection (D21): measured system behaviour times editable, labelled assumptions.

Nothing here invents a number. Every input is either measured by the eval or live run,
or is an assumption the presenter can change and the page labels as one.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Assumptions:
    """Inputs the brief does not give. Defaults are illustrative and labelled as such on the page."""

    invoices_per_year: int = 40_000  # assumption: the brief gives no volume
    current_annual_loss: float = 2_000_000.0  # brief
    current_error_rate: float = 0.30  # brief
    current_cycle_days: float = 5.0  # brief
    review_minutes: float = 15.0  # assumption: one person-review of an escalated invoice
    loaded_hourly_cost: float = 60.0  # assumption: AP specialist, fully loaded
    review_turnaround_days: float = 1.0  # assumption: inbox service level


@dataclass(frozen=True)
class Measured:
    """What the system did on the 27 test invoices (eval) and on the live run."""

    escalation_rate: float
    trap_catch_rate: float
    cost_per_invoice: float
    seconds_per_invoice: float


@dataclass(frozen=True)
class Projection:
    """Annual projection."""

    model_cost: float
    review_cost: float
    total_cost: float
    savings: float
    automated_share: float
    cycle_days: float


def project(a: Assumptions, m: Measured) -> Projection:
    """Annual cost and cycle time if the system handled the year's invoices the way it handled the tests."""
    model_cost = a.invoices_per_year * m.cost_per_invoice
    reviewed = a.invoices_per_year * m.escalation_rate
    review_cost = reviewed * a.review_minutes / 60 * a.loaded_hourly_cost
    total = model_cost + review_cost
    automated = 1 - m.escalation_rate
    cycle = automated * (m.seconds_per_invoice / 86_400) + m.escalation_rate * a.review_turnaround_days
    return Projection(
        model_cost=model_cost,
        review_cost=review_cost,
        total_cost=total,
        savings=a.current_annual_loss - total,
        automated_share=automated,
        cycle_days=cycle,
    )
