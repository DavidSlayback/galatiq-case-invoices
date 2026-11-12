"""Offline model: replays hand-written golden outputs keyed by input-file hash (A4).

A golden is what a faithful model would return for that file, so the rest of
the pipeline (reconciliation, rules, routing) runs for real. A missing golden
is an error, never a guess.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "golden"


class MissingFixture(LookupError):
    """No golden output exists for this input in offline mode."""


@cache
def _index(kind: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((GOLDEN_DIR / kind).glob("*.json")):
        g = json.loads(p.read_text(encoding="utf-8"))
        out[g["file_sha256"]] = g
    return out


def golden(kind: str, file_sha256: str, source: str) -> dict[str, Any]:
    """Look up the golden output of one agent for one input file.

    Args:
        kind: Agent kind (``extract``, ``vp``, ``critic``).
        file_sha256: Hash of the input file.
        source: Path, for the error message.

    Raises:
        MissingFixture: No golden for this file.
    """
    g = _index(kind).get(file_sha256)
    if g is None:
        raise MissingFixture(f"no offline '{kind}' golden for {source} (sha256 {file_sha256[:12]}…)")
    return g


def replay_model(output: dict[str, Any], name: str) -> FunctionModel:
    """A model that answers with ``output`` as the agent's structured result."""

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=output)])

    return FunctionModel(respond, model_name=name)
