"""Model selection for the agents."""

from pydantic_ai.models import Model

from invoice_agents.agents.offline import golden, replay_model
from invoice_agents.models import RawDocument
from invoice_agents.settings import Settings


def is_offline(settings: Settings) -> bool:
    """Offline replay unless a live model is configured."""
    return settings.offline or settings.model in (None, "offline")


def resolve(settings: Settings, kind: str, doc: RawDocument, attempt: int = 0) -> Model | str:
    """Model for one agent call: a golden replay offline, else the configured model string.

    A golden may script successive answers in ``attempts``; attempt ``n`` gets the
    n-th (the last one repeats). Otherwise every attempt gets ``output``.
    """
    if is_offline(settings):
        g = golden(kind, doc.file_sha256, doc.path)
        answers = g.get("attempts") or [g["output"]]
        return replay_model(answers[min(attempt, len(answers) - 1)], name=f"offline:{kind}")
    assert settings.model is not None
    return settings.model
