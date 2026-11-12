"""Per-invoice tokens, time and API-equivalent cost from a run's trace (NFR-11, D21).

Prices are published per-million-token API rates, used to express cost even when
a subscription CLI bills nothing per call. They come from third-party price
trackers on 2026-11-12, because the vendors' own pages did not return figures.
Check them before quoting.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

PRICES_AS_OF = "2026-11-12"
# model name fragment -> (USD per 1M input tokens, USD per 1M output tokens)
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "grok-4.7": (Decimal("2.00"), Decimal("6.00")),
    "haiku": (Decimal("0.10"), Decimal("0.50")),  # Claude Haiku 5.5, prompts under 100K tokens
}
MILLION = Decimal(1_000_000)


def price(model: str | None) -> tuple[Decimal, Decimal] | None:
    """Per-million prices for a model spec, or None if unknown (offline replay costs nothing)."""
    return next((p for frag, p in PRICES.items() if model and frag in model), None)


@dataclass(frozen=True)
class Usage:
    """What one invoice's run consumed."""

    calls: int
    tokens_in: int
    tokens_out: int
    seconds: float

    def cost(self, model: str | None) -> Decimal | None:
        """API-equivalent USD; None when the model has no listed price ("unknown", never 0)."""
        if model == "offline":
            return Decimal(0)
        p = price(model)
        if p is None:
            return None
        return ((self.tokens_in * p[0] + self.tokens_out * p[1]) / MILLION).quantize(Decimal("0.0001"))


def usage(trace_path: Path) -> Usage:
    """Sum the agent calls recorded in one run's JSONL trace."""
    if not trace_path.exists():
        return Usage(0, 0, 0, 0.0)
    lines = [json.loads(x) for x in trace_path.read_text().splitlines()]
    calls = [t for t in lines if "tokens" in t]
    return Usage(
        calls=len(calls),
        tokens_in=sum(t["tokens"][0] for t in calls),
        tokens_out=sum(t["tokens"][1] for t in calls),
        seconds=max((t["t"] for t in lines), default=0.0),
    )
