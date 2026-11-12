"""Run agents on subscription CLIs (D31): Grok through ``cursor-agent``, Claude through ``claude``.

Each call renders the PydanticAI conversation and the output JSON Schema into
one prompt, runs the CLI in a fresh empty temp directory with tools off or
read-only, and hands the parsed JSON back as the agent's structured output. The
agents, validators and retry loops do not know a CLI is answering.

Sandboxing matters: invoice text is untrusted, and both CLIs are agents that
can act. Cursor runs in read-only ``ask`` mode; Claude runs with no tools (or
``Read`` only, for page images), no MCP servers, no settings and no saved session.
Neither can write or run commands. Read-only modes can still read files outside
the temp dir, so do not run the CLI backends on a machine holding secrets that an
injected invoice could ask the model to quote.
"""

import asyncio
import json
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryFeedbackPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

Tool = Literal["cursor", "claude"]
TIMEOUT_S = 180
QUOTA = re.compile(r"rate.?limit|quota|usage limit|too many requests|out of credits", re.IGNORECASE)


class BackendQuotaError(RuntimeError):
    """The subscription reported a quota or rate limit; the run should stop, not retry (stop condition)."""


@dataclass
class CliCall:
    """What one CLI call was given and returned (kept for traces and tests)."""

    argv: list[str]
    cwd: str
    seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    images: int = 0
    error: str | None = None


@dataclass
class CliBackend:
    """A CLI-backed model. ``calls`` records every invocation."""

    tool: Tool
    model: str
    timeout_s: int = TIMEOUT_S
    calls: list[CliCall] = field(default_factory=list[CliCall])

    def as_model(self) -> FunctionModel:
        """A PydanticAI model that answers through this CLI."""
        return FunctionModel(self._respond, model_name=f"cli:{self.tool}:{self.model}")

    async def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not info.output_tools:
            raise ValueError("CLI bridge supports structured-output agents only")
        out_tool = info.output_tools[0]
        with tempfile.TemporaryDirectory(prefix="invoice-cli-") as cwd:
            prompt, images = render(messages, info.instructions, out_tool.parameters_json_schema, Path(cwd))
            argv = self.argv(prompt, info.instructions or "", out_tool.parameters_json_schema, bool(images))
            call = CliCall(argv=argv, cwd=cwd, images=len(images))
            self.calls.append(call)
            stdout, stderr, rc, call.seconds = await _run(argv, cwd, self.timeout_s, prompt)
        if QUOTA.search(stderr) or (rc != 0 and QUOTA.search(stdout)):
            raise BackendQuotaError(f"{self.tool} reported a quota or rate limit: {(stderr or stdout)[:300]}")
        try:
            payload, call.tokens_in, call.tokens_out = self.parse(stdout)
        except ValueError as e:
            call.error = f"rc={rc} {e}; stderr={stderr[:300]}"
            # A text reply makes PydanticAI ask again ("use the output tool"); after its retry
            # budget the agent raises, and the graph escalates instead of crashing.
            return ModelResponse(parts=[TextPart(f"(backend returned no usable JSON: {e})")])
        return ModelResponse(
            parts=[ToolCallPart(tool_name=out_tool.name, args=payload)],
            usage=RequestUsage(input_tokens=call.tokens_in, output_tokens=call.tokens_out),
            model_name=f"cli:{self.tool}:{self.model}",
        )

    def argv(self, prompt: str, system: str, schema: dict[str, Any], images: bool) -> list[str]:
        """Command line for one call. Never grants write or shell tools."""
        if self.tool == "cursor":
            # Cursor has no separate system prompt or schema flag; both go into the prompt.
            return ["cursor-agent", "-p", "--trust", "--mode", "ask", "--output-format", "json",
                    "--model", self.model]  # fmt: skip
        return [
            "claude", "-p", "--output-format", "json", "--model", self.model,
            "--tools", "Read" if images else "",
            "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
            "--system-prompt", system or "Return only the requested JSON.",
            "--json-schema", json.dumps(schema),
        ]  # fmt: skip

    def parse(self, stdout: str) -> tuple[dict[str, Any], int, int]:
        """Structured output and token counts from the CLI's JSON envelope.

        Raises:
            ValueError: No JSON object could be recovered.
        """
        try:
            env = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f"envelope is not JSON: {stdout[:200]!r}") from e
        if env.get("is_error"):
            raise ValueError(f"backend error: {str(env.get('result'))[:200]}")
        usage = env.get("usage") or {}
        t_in = int(usage.get("input_tokens") or usage.get("inputTokens") or 0)
        t_out = int(usage.get("output_tokens") or usage.get("outputTokens") or 0)
        so = env.get("structured_output")
        if isinstance(so, dict):
            return so, t_in, t_out  # pyright: ignore[reportUnknownVariableType]
        return extract_json(str(env.get("result") or "")), t_in, t_out


def extract_json(text: str) -> dict[str, Any]:
    """The JSON object in a model reply, tolerating code fences and surrounding prose.

    Raises:
        ValueError: No JSON object found.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj  # pyright: ignore[reportUnknownVariableType]
    raise ValueError(f"no JSON object in reply: {text[:200]!r}")


def render(
    messages: list[ModelMessage], instructions: str | None, schema: dict[str, Any], cwd: Path
) -> tuple[str, list[Path]]:
    """Flatten the conversation into one prompt; page images are written into ``cwd`` and referenced by name."""
    out: list[str] = []
    images: list[Path] = []
    if instructions:
        out.append(f"# Instructions\n{instructions}")
    for m in messages:
        if isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, ToolCallPart):
                    out.append(f"# Your previous answer\n{p.args_as_json_str()}")
            continue
        assert isinstance(m, ModelRequest)
        for p in m.parts:
            if isinstance(p, SystemPromptPart):
                out.append(f"# Instructions\n{p.content}")
            elif isinstance(p, UserPromptPart):
                contents = [p.content] if isinstance(p.content, str) else list(p.content)
                for c in contents:
                    if isinstance(c, str):
                        out.append(c)
                    elif isinstance(c, BinaryContent) and c.media_type.startswith("image/"):
                        img = cwd / f"page_{len(images) + 1}.png"
                        img.write_bytes(c.data)
                        images.append(img)
                        out.append(f"[Page image: {img.name} in the current directory. Read it.]")
            elif isinstance(p, RetryFeedbackPart):
                out.append(f"# Your previous answer was rejected\n{p.model_response()}")
            elif isinstance(p, ToolReturnPart):
                # Output-tool validation failures come back as tool returns marked for retry.
                out.append(f"# Feedback on your previous answer\n{p.model_response_str()}")
    out.append(
        "# Output\nReply with exactly one JSON object matching this JSON Schema, and nothing else:\n"
        + json.dumps(schema)
    )
    return "\n\n".join(out), images


async def _run(argv: list[str], cwd: str, timeout_s: int, prompt: str) -> tuple[str, str, int, float]:
    """Run the CLI with the prompt on stdin: an argv string is capped at 128 KiB on Linux (B8)."""
    t0 = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip
    except FileNotFoundError:
        return "", f"{argv[0]} is not installed", 127, 0.0
    except OSError as e:
        return "", f"{argv[0]} could not start: {e}", 126, 0.0
    try:
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return "", f"timed out after {timeout_s}s", 124, time.perf_counter() - t0
    rc = proc.returncode if proc.returncode is not None else -1
    return out.decode(errors="replace"), err.decode(errors="replace"), rc, time.perf_counter() - t0
