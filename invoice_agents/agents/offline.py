"""Offline model: replays hand-written golden outputs keyed by input-file hash (A4).

A golden is what a faithful model would return for that file, so the rest of
the pipeline (reconciliation, rules, routing) runs for real. A missing golden
is an error, never a guess.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "golden"


class MissingFixture(LookupError):
    """No golden output exists for this input in offline mode."""


def _index(directory: Path) -> dict[str, dict[str, Any]]:
    """Goldens in ``directory`` by input-file hash.

    The cache is keyed on each file's path, mtime and size, so a directory rewritten in place is re-read (D44).
    """
    files = sorted(directory.glob("*.json"))
    return _load(tuple((p, p.stat().st_mtime_ns, p.stat().st_size) for p in files))


@lru_cache(maxsize=64)
def _load(signature: tuple[tuple[Path, int, int], ...]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p, _, _ in signature:
        g = json.loads(p.read_text(encoding="utf-8"))
        out[g["file_sha256"]] = g
    return out


def golden(kind: str, file_sha256: str, source: str, golden_dir: Path = GOLDEN_DIR) -> dict[str, Any]:
    """Look up the golden output of one agent for one input file.

    Args:
        kind: Agent kind (``extract``, ``vp``, ``critic``).
        file_sha256: Hash of the input file.
        source: Path, for the error message.
        golden_dir: Replay source; ``Settings.golden_dir`` picks it per run.

    Returns:
        The golden record: its ``output``, or successive scripted answers in ``attempts``
        (:func:`invoice_agents.agents.models.resolve` picks one per attempt).

    Raises:
        MissingFixture: No golden for this file.
    """
    g = _index(golden_dir / kind).get(file_sha256)
    if g is None:
        raise MissingFixture(f"no offline '{kind}' golden for {source} (sha256 {file_sha256[:12]}…)")
    return g


def replay_model(output: dict[str, Any], name: str) -> FunctionModel:
    """A model that answers with ``output`` as the agent's structured result."""

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=output)])

    return FunctionModel(respond, model_name=name)
