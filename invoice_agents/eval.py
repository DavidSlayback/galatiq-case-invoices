"""Eval harness: run every file in eval/expected_outcomes.yaml against a fresh database and score it (D20)."""

import contextlib
import io
import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.table import Table

from invoice_agents import graph, ledger
from invoice_agents.agents import models, offline
from invoice_agents.agents.models import is_offline
from invoice_agents.agents.offline import MissingFixture
from invoice_agents.loaders import file_sha256
from invoice_agents.models import Invoice
from invoice_agents.normalize import RawExtraction, to_invoice
from invoice_agents.seed import reset
from invoice_agents.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "eval" / "expected_outcomes.yaml"


@dataclass(frozen=True)
class Row:
    """One scored file."""

    path: str
    expected: str
    actual: str
    decided_by: str
    missing: list[str]
    unexpected: list[str]
    seconds: float
    pending: str | None = None
    error: str | None = None
    rule_ids: list[str] = field(default_factory=list[str])
    calls: int = 0
    tokens: int = 0
    extraction_diff: list[str] = field(default_factory=list[str])

    @property
    def passed(self) -> bool:
        """Matches the expectation."""
        return self.error is None and self.expected == self.actual and not self.missing and not self.unexpected


def load_expected(path: Path = EXPECTED) -> dict[str, dict[str, Any]]:
    """Expected outcomes keyed by repo-relative path, in file order."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _live_extraction(trace_path: Path) -> Invoice | None:
    """The last extraction the model produced in a run, from its trace."""
    if not trace_path.exists():
        return None
    lines = [json.loads(x) for x in trace_path.read_text().splitlines()]
    ex = [t for t in lines if t["node"] == "extract" and "invoice" in t]
    return Invoice.model_validate(ex[-1]["invoice"]) if ex else None


def extraction_diff(path: Path, live: Invoice) -> list[str]:
    """Core fields where a live extraction differs from the golden for the same file (A4)."""
    try:
        g = offline.golden("extract", file_sha256(path.read_bytes()), str(path))
    except offline.MissingFixture:
        return ["no golden"]
    want = ledger.core(to_invoice(RawExtraction.model_validate(g["output"])))
    got = ledger.core(live)
    return [f"{k}: golden {want[k]!r} vs live {got[k]!r}" for k in ledger.CORE_FIELDS if want[k] != got[k]]


def run(
    settings: Settings, expected: dict[str, dict[str, Any]] | None = None, record_dir: Path | None = None
) -> list[Row]:
    """Process every expected file in order on a throwaway database and score each.

    Args:
        settings: Model and date settings; the database and runs paths are replaced with temp ones.
        expected: Expectations to use instead of the YAML file.
        record_dir: With a live model, write each file's extraction here for review against the goldens.
    """
    live = not is_offline(settings)
    cli = (
        models.backend(settings.model)
        if live and settings.model and models.CLI_SPEC.fullmatch(settings.model)
        else None
    )
    expected = expected if expected is not None else load_expected()
    rows: list[Row] = []
    with tempfile.TemporaryDirectory() as tmp:
        s = settings.with_overrides(db_path=Path(tmp) / "eval.db", runs_dir=settings.runs_dir / "eval")
        conn = reset(s.db_path)
        for rel, exp in expected.items():
            t0 = time.perf_counter()
            n0 = len(cli.calls) if cli else 0
            try:
                with contextlib.redirect_stdout(io.StringIO()):  # mock_payment prints; keep the scorecard clean
                    o = graph.process_sync(ROOT / rel, s, conn)
            except MissingFixture as e:
                rows.append(Row(rel, exp["status"], "error", "", [], [], 0.0, exp.get("pending"), str(e)))
                continue
            ids = [f.rule_id for f in o.findings]
            actor = o.decision.actor if o.decision else ""
            new_calls = cli.calls[n0:] if cli else []
            diff: list[str] = []
            got = _live_extraction(s.runs_dir / f"{o.run_id}.jsonl") if live else None
            if got is not None:
                diff = extraction_diff(ROOT / rel, got)
                if record_dir is not None:
                    out = record_dir / f"{Path(rel).name}.json"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(got.model_dump_json(indent=2), encoding="utf-8")
            want_actor = exp.get("decided_by")
            rows.append(
                Row(
                    path=rel,
                    expected=exp["status"],
                    actual=o.status.value,
                    decided_by=actor,
                    missing=[r for r in exp.get("requires", []) if r not in ids]
                    + ([f"decided_by={want_actor}"] if want_actor and want_actor != actor else []),
                    unexpected=[r for r in exp.get("forbids", []) if r in ids],
                    seconds=round(time.perf_counter() - t0, 3),
                    pending=exp.get("pending"),
                    rule_ids=sorted(set(ids)),
                    calls=len(new_calls),
                    tokens=sum(c.tokens_in + c.tokens_out for c in new_calls),
                    extraction_diff=diff,
                )
            )
        conn.close()
    return rows


def failures(rows: list[Row]) -> list[Row]:
    """Rows that fail and are not pending."""
    return [r for r in rows if not r.passed and not r.pending]


def table(rows: list[Row]) -> Table:
    """Rich scorecard."""
    t = Table("File", "Expected", "Actual", "By", "Missing / unexpected", "s", title="Eval scorecard")
    for r in rows:
        mark = "[green]PASS[/green]" if r.passed else ("[yellow]PENDING[/yellow]" if r.pending else "[red]FAIL[/red]")
        problems = ", ".join(r.missing + [f"+{u}" for u in r.unexpected]) or (r.error or "")
        t.add_row(f"{mark} {Path(r.path).name}", r.expected, r.actual, r.decided_by, problems, f"{r.seconds:.2f}")
    return t


def markdown(rows: list[Row], model: str) -> str:
    """Scorecard as Markdown for docs/scorecard.md."""
    passed = sum(r.passed for r in rows)
    pending = sum(1 for r in rows if r.pending and not r.passed)
    out = [
        "# Eval scorecard",
        "",
        f"Model: `{model}`. {passed}/{len(rows)} pass, {pending} pending, {len(failures(rows))} failing.",
        "Expectations: [eval/expected_outcomes.yaml](../eval/expected_outcomes.yaml).",
        "",
        "| File | Result | Expected | Actual | Decided by | Rules fired |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        res = "PASS" if r.passed else ("PENDING" if r.pending else "FAIL")
        cells = [Path(r.path).name, res, r.expected, r.actual, r.decided_by or "-", ", ".join(r.rule_ids) or "-"]
        out.append("| " + " | ".join(cells) + " |")
    if any(r.calls for r in rows):
        out += [
            "",
            "## Live model usage and extraction differences from the goldens",
            "",
            f"Total: {sum(r.calls for r in rows)} model calls, {sum(r.tokens for r in rows):,} tokens, "
            f"{sum(r.seconds for r in rows) / 60:.1f} minutes.",
            "",
            "| File | Calls | Tokens | Seconds | Extraction differences |",
            "|---|---|---|---|---|",
        ]
        for r in rows:
            d = "; ".join(r.extraction_diff) or "none"
            out.append(f"| {Path(r.path).name} | {r.calls} | {r.tokens:,} | {r.seconds:.0f} | {d} |")
    return "\n".join(out) + "\n"
