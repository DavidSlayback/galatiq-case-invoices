import json
import os
import sqlite3
import stat
from pathlib import Path

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from invoice_agents import graph
from invoice_agents.agents import cli_bridge, models
from invoice_agents.agents.cli_bridge import BackendQuotaError, extract_json
from invoice_agents.agents.extractor import extractor
from invoice_agents.models import Status
from invoice_agents.settings import Settings
from tests.conftest import INVOICES, ROOT

FAKE = Path(__file__).parent / "fake_bin" / "fake_cli.py"
GOLDEN_1004 = json.loads((ROOT / "fixtures/golden/extract/invoice_1004_json.json").read_text())["output"]


@pytest.fixture
def fake_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put fake `cursor-agent` and `claude` first on PATH; returns the call log."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("cursor-agent", "claude"):
        exe = bindir / name
        exe.write_text(f'#!/bin/sh\nexec {os.sys.executable} {FAKE} "$@"\n')  # type: ignore[attr-defined]
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLI_LOG", str(log))
    monkeypatch.setenv("FAKE_CLI_ANSWER", json.dumps(GOLDEN_1004))
    models._backends.clear()  # pyright: ignore[reportPrivateUsage]
    return log


def calls(log: Path) -> list[dict[str, object]]:
    return [json.loads(x) for x in log.read_text().splitlines()]


@pytest.mark.parametrize("spec", ["cli:cursor:grok-4.7-low-fast", "cli:claude:haiku"])
def test_bridge_runs_pipeline_and_sandboxes(fake_path: Path, conn: sqlite3.Connection, tmp_path: Path, spec: str):
    s = Settings(model=spec, db_path=tmp_path / "t.db", runs_dir=tmp_path / "runs")
    o = graph.process_sync(INVOICES / "invoice_1004.json", s, conn)
    assert o.status == Status.PAID
    (c,) = calls(fake_path)
    argv = [str(a) for a in c["argv"]]  # type: ignore[union-attr]
    assert c["files"] == [] and "invoice-cli-" in str(c["cwd"])  # fresh, empty temp dir
    assert "--force" not in argv and "--yolo" not in argv and "-f" not in argv
    if "cursor" in spec:
        assert argv[argv.index("--mode") + 1] == "ask"
    else:
        assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv
        assert "--system-prompt" in argv and "--no-session-persistence" in argv
        assert argv[argv.index("--setting-sources") + 1] == ""


@pytest.mark.parametrize("mode", ["garbage", "error"])
async def test_unusable_output_retries_then_raises(fake_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str):
    monkeypatch.setenv("FAKE_CLI_MODE", mode)
    with pytest.raises(UnexpectedModelBehavior):
        await extractor.run("doc", model=models.backend("cli:claude:haiku").as_model())
    assert len(calls(fake_path)) == 3  # first try + 2 retries


def test_graph_escalates_when_model_keeps_failing(
    fake_path: Path, monkeypatch: pytest.MonkeyPatch, conn: sqlite3.Connection, tmp_path: Path
):
    monkeypatch.setenv("FAKE_CLI_MODE", "garbage")
    s = Settings(model="cli:cursor:grok-4.7-low-fast", db_path=tmp_path / "t.db", runs_dir=tmp_path / "runs")
    o = graph.process_sync(INVOICES / "invoice_1004.json", s, conn)
    assert o.status == Status.ESCALATED
    assert conn.execute("SELECT reason FROM inbox").fetchone()[0] == "extraction_failed"


async def test_quota_stops_the_run(fake_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "quota")
    with pytest.raises(BackendQuotaError):
        await extractor.run("doc", model=models.backend("cli:cursor:x").as_model())


async def test_timeout_is_retried_not_hung(fake_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "sleep")
    b = models.backend("cli:claude:haiku")
    b.timeout_s = 1
    with pytest.raises(UnexpectedModelBehavior):
        await extractor.run("doc", model=b.as_model())
    assert all(c.error and "rc=124" in c.error for c in b.calls)


def test_missing_cli_is_a_clear_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PATH", str(tmp_path))
    models._backends.clear()  # pyright: ignore[reportPrivateUsage]
    b = models.backend("cli:cursor:x")
    with pytest.raises(UnexpectedModelBehavior):
        extractor.run_sync("doc", model=b.as_model())
    assert "not installed" in (b.calls[0].error or "")


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('Sure! ```json\n{"a": 1}\n``` done') == {"a": 1}
    assert extract_json('noise {"a": {"b": 2}} tail') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json here")


@pytest.mark.parametrize(
    ("env", "which", "expected"),
    [
        ({"XAI_API_KEY": "x"}, set[str](), "xai:grok-4.7"),
        ({"ANTHROPIC_API_KEY": "x"}, {"cursor-agent"}, "anthropic:claude-haiku-5-5"),
        ({}, {"cursor-agent", "claude"}, models.DEFAULT_CURSOR),
        ({}, {"claude"}, models.DEFAULT_CLAUDE),
        ({}, set[str](), "offline"),
    ],
)
def test_detect_order(env: dict[str, str], which: set[str], expected: str):
    spec, why = models.detect(env, lambda n: f"/bin/{n}" if n in which else None)
    assert spec == expected and why


def test_render_writes_images_into_sandbox(tmp_path: Path):
    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    msg = ModelRequest(
        parts=[UserPromptPart(content=["read this", BinaryContent(data=b"\x89PNG", media_type="image/png")])]
    )
    prompt, images = cli_bridge.render([msg], "inst", {"type": "object"}, tmp_path)
    assert images == [tmp_path / "page_1.png"] and "page_1.png" in prompt and '"type": "object"' in prompt
