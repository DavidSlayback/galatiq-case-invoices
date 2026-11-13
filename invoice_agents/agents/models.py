"""Model selection for the agents: offline replay, subscription CLIs, or any PydanticAI API model."""

import os
import re
import shutil
from collections.abc import Callable, Mapping

from pydantic_ai.models import Model

from invoice_agents.agents.cli_bridge import CliBackend
from invoice_agents.agents.offline import golden, replay_model
from invoice_agents.models import RawDocument
from invoice_agents.settings import Settings

CLI_SPEC = re.compile(r"cli:(cursor|claude):(.+)")
DEFAULT_CURSOR = "cli:cursor:grok-4.7-medium-fast"
DEFAULT_CLAUDE = "cli:claude:haiku"
_backends: dict[str, CliBackend] = {}


def is_offline(settings: Settings) -> bool:
    """Offline replay unless a live model is configured."""
    return settings.offline or settings.model in (None, "offline")


def backend(spec: str) -> CliBackend:
    """The shared CLI backend for a ``cli:<tool>:<model>`` spec (one per spec, so calls accumulate)."""
    m = CLI_SPEC.fullmatch(spec)
    if not m:
        raise ValueError(f"not a CLI model spec: {spec!r}")
    if spec not in _backends:
        _backends[spec] = CliBackend(tool=m.group(1), model=m.group(2))  # type: ignore[arg-type]
    return _backends[spec]


def resolve(settings: Settings, kind: str, doc: RawDocument, attempt: int = 0) -> Model | str:
    """Model for one agent call.

    Offline: a golden replay (a golden may script successive answers in ``attempts``;
    attempt ``n`` gets the n-th, the last one repeats). ``cli:*``: the subscription
    bridge. Anything else is passed to PydanticAI as a model string.
    """
    if is_offline(settings):
        g = golden(kind, doc.file_sha256, doc.path, settings.golden_dir)
        answers = g.get("attempts") or [g["output"]]
        return replay_model(answers[min(attempt, len(answers) - 1)], name=f"offline:{kind}")
    assert settings.model is not None
    if CLI_SPEC.fullmatch(settings.model):
        return backend(settings.model).as_model()
    return settings.model


def detect(env: Mapping[str, str] | None = None, which: Callable[[str], str | None] = shutil.which) -> tuple[str, str]:
    """Pick a backend when none is configured (D32): xAI key, other API key, logged-in CLI, then offline.

    Returns:
        The model spec and a one-line reason, shown to the user.
    """
    e = os.environ if env is None else env
    if e.get("XAI_API_KEY"):
        return "xai:grok-4.7", "XAI_API_KEY is set"
    if e.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-haiku-5-5", "ANTHROPIC_API_KEY is set"
    if which("cursor-agent"):
        return DEFAULT_CURSOR, "cursor-agent is installed (Grok on your Cursor plan)"
    if which("claude"):
        return DEFAULT_CLAUDE, "claude is installed (Claude on your Claude plan)"
    return "offline", "no API key or model CLI found; replaying recorded answers"
