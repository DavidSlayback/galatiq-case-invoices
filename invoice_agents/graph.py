"""The processing graph: load → extract ⇄ reconcile → validate → route → pay / reject / escalate.

Built with pydantic-graph (D11). Every step records its business event through
``db`` and a trace line through ``Tracer``; decisions about what to do live in
the stage modules (rules, approval, payment), not here.
"""

import asyncio
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai.messages import ModelMessage
from pydantic_graph import GraphBuilder, StepContext

from invoice_agents import approval, db, fx, payment, reconcile, rules
from invoice_agents.agents import extractor, reviewers
from invoice_agents.approval import Approve, AutoApprove, HumanReview, Objected, Proposed, Reject, VpReview
from invoice_agents.ledger import key_for
from invoice_agents.loaders import LoadError, load
from invoice_agents.models import (
    Decision,
    EventType,
    Finding,
    Invoice,
    InvoiceKey,
    Outcome,
    RawDocument,
    Status,
)
from invoice_agents.settings import Settings
from invoice_agents.trace import Tracer, new_run_id

MAX_EXTRACT_RETRIES = 2  # D14


@dataclass
class Deps:
    """Run-wide services."""

    conn: sqlite3.Connection
    settings: Settings
    tracer: Tracer


@dataclass
class State:
    """Mutable per-invoice state carried between steps."""

    path: Path
    run_id: str
    doc: RawDocument | None = None
    invoice: Invoice | None = None
    key: InvoiceKey | None = None
    attempt: int = 0
    feedback: str | None = None
    history: list[ModelMessage] = field(default_factory=list[ModelMessage])
    findings: list[Finding] = field(default_factory=list[Finding])
    model_name: str = ""
    review_brief: str = ""
    vp_history: list[ModelMessage] = field(default_factory=list[ModelMessage])


@dataclass(frozen=True)
class Loaded:
    """A readable document."""

    doc: RawDocument


@dataclass(frozen=True)
class LoadFailed:
    """The file could not be loaded."""

    reason: str


@dataclass(frozen=True)
class Extracted:
    """The extractor's answer for this attempt."""

    invoice: Invoice


@dataclass(frozen=True)
class Retry:
    """Reconciliation failed; try extraction again with this feedback."""

    feedback: str


@dataclass(frozen=True)
class Reconciled:
    """Extraction accepted, possibly with an ARITHMETIC_MISMATCH finding."""

    invoice: Invoice


g = GraphBuilder(state_type=State, deps_type=Deps, input_type=Path, output_type=Outcome)


@g.step
async def load_file(ctx: StepContext[State, Deps, Path]) -> Loaded | LoadFailed:
    """Read the file into a RawDocument."""
    try:
        doc = load(ctx.inputs)
    except LoadError as e:
        ctx.deps.tracer.log("load", path=str(ctx.inputs), error=str(e))
        return LoadFailed(str(e))
    ctx.state.doc = doc
    ctx.deps.tracer.log("load", path=doc.path, format=doc.format, sha256=doc.file_sha256)
    return Loaded(doc)


@g.step
async def extract(ctx: StepContext[State, Deps, Loaded]) -> Extracted:
    """Ask the extraction agent for a typed invoice."""
    s = ctx.state
    result = await extractor.extract(ctx.inputs.doc, ctx.deps.settings, s.feedback, s.history, s.attempt)
    s.history, s.model_name = result.messages, result.model_name
    ctx.deps.tracer.log(
        "extract", attempt=s.attempt, model=result.model_name, invoice=result.invoice.model_dump(mode="json")
    )
    return Extracted(result.invoice)


@g.step
async def reconcile_step(ctx: StepContext[State, Deps, Extracted]) -> Reconciled | Retry:
    """Check the arithmetic; retry extraction with the specific mismatch, at most twice (D14)."""
    s, inv = ctx.state, ctx.inputs.invoice
    problems = reconcile.mismatches(inv)
    ctx.deps.tracer.log("reconcile", attempt=s.attempt, mismatches=problems)
    if problems and s.attempt < MAX_EXTRACT_RETRIES:
        return Retry("\n".join(problems))
    if problems:
        s.findings.append(
            Finding(
                rule_id="ARITHMETIC_MISMATCH",
                severity="hard",
                message="; ".join(problems),
                evidence={"attempts": s.attempt + 1},
            )
        )
    assert s.doc is not None
    s.invoice, s.key = inv, key_for(inv, s.doc.file_sha256)
    d = ctx.deps
    db.record(
        d.conn, s.key, EventType.RECEIVED, actor="intake", run_id=s.run_id,
        payload={"path": s.doc.path, "sha256": s.doc.file_sha256, "format": s.doc.format},
        status=Status.RECEIVED, source_path=s.doc.path, total=inv.total, currency=inv.currency,
    )  # fmt: skip
    db.record(
        d.conn, s.key, EventType.EXTRACTED, actor="extractor", run_id=s.run_id,
        payload={"model": s.model_name, "attempts": s.attempt + 1, "mismatches": problems},
        status=Status.EXTRACTED,
    )  # fmt: skip
    return Reconciled(inv)


@g.step
async def retry(ctx: StepContext[State, Deps, Retry]) -> Loaded:
    """Feed the mismatch back to the extractor."""
    ctx.state.attempt += 1
    ctx.state.feedback = ctx.inputs.feedback
    assert ctx.state.doc is not None
    return Loaded(ctx.state.doc)


@g.step
async def validate(ctx: StepContext[State, Deps, Reconciled]) -> approval.Route:
    """Run the rules and pick the approval route."""
    s, d, inv = ctx.state, ctx.deps, ctx.inputs.invoice
    assert s.key is not None
    s.findings += rules.validate(inv, d.conn, d.settings.as_of)
    with d.conn:
        d.conn.executemany(
            "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(s.run_id, *s.key, f.rule_id, f.severity, f.message, db.json_dumps(f.evidence)) for f in s.findings],
        )
    db.record(
        d.conn, s.key, EventType.VALIDATED, actor="rules", run_id=s.run_id,
        payload={"findings": [f.model_dump() for f in s.findings]}, status=Status.VALIDATED,
    )  # fmt: skip
    r = approval.route(inv, s.findings, fx.to_usd(inv.total, inv.currency, fx.rates(d.conn)))
    d.tracer.log("route", route=type(r).__name__, findings=[f.rule_id for f in s.findings])
    return r


@g.step
async def vp_propose(ctx: StepContext[State, Deps, VpReview | Objected]) -> Proposed:
    """The VP agent proposes approve or reject; on later rounds it answers the critic's objections."""
    s, r = ctx.state, ctx.inputs
    assert s.doc is not None
    round_ = r.round + 1 if isinstance(r, Objected) else 0
    if round_ == 0:
        s.review_brief = reviewers.case_brief(r.invoice, r.findings, r.usd_total)
    objections = list(r.objections) if isinstance(r, Objected) else []
    p, s.vp_history = await reviewers.propose(
        s.doc, ctx.deps.settings, s.review_brief, objections, s.vp_history, round_
    )
    ctx.deps.tracer.log("vp_propose", round=round_, proposal=p.model_dump())
    d = Decision(kind=p.decision, actor="vp_agent", reasons=p.reasons, cited_rule_ids=p.cited_rule_ids)
    return Proposed(r.invoice, r.findings, r.usd_total, decision=d, round=round_)


@g.step
async def critique(ctx: StepContext[State, Deps, Proposed]) -> Approve | Reject | Objected | HumanReview:
    """The critic checks the proposal; agreement is final (after the guardrail), deadlock goes to a human."""
    s, r, d = ctx.state, ctx.inputs, ctx.deps
    assert s.doc is not None and r.decision is not None and s.key is not None
    known = {f.rule_id for f in r.findings}
    invented = [i for i in r.decision.cited_rule_ids if i not in known]
    if invented:  # checked in code: a citation must name a finding that exists
        verdict = reviewers.Critique(agrees=False, objections=[f"cited rule IDs not in the findings: {invented}"])
    else:
        verdict = await reviewers.critique(s.doc, d.settings, s.review_brief, r.decision, r.round)
    d.tracer.log("critique", round=r.round, verdict=verdict.model_dump())
    if verdict.agrees:
        decision, overridden = approval.guard(r.decision, r.findings)
        if overridden:
            db.record(d.conn, s.key, EventType.GUARDRAIL_OVERRIDE, actor="guardrail", run_id=s.run_id,
                      payload={"proposed": r.decision.model_dump(), "final": decision.model_dump()})  # fmt: skip
        if decision.kind == "approve":
            return Approve(r.invoice, r.findings, r.usd_total, decision=decision)
        return Reject(r.invoice, r.findings, r.usd_total, decision=decision)
    if r.round + 1 < approval.MAX_REVIEW_ROUNDS:
        return Objected(r.invoice, r.findings, r.usd_total, objections=tuple(verdict.objections), round=r.round)
    return HumanReview(r.invoice, r.findings, r.usd_total, reason="vp_critic_disagree")


def _decided(ctx: StepContext[State, Deps, object], decision: Decision) -> InvoiceKey:
    s = ctx.state
    assert s.key is not None
    db.record(
        ctx.deps.conn, s.key, EventType.DECIDED, actor=decision.actor, run_id=s.run_id,
        payload=decision.model_dump(),
    )  # fmt: skip
    return s.key


@g.step
async def pay(ctx: StepContext[State, Deps, AutoApprove | Approve]) -> Outcome:
    """Pay an approved invoice."""
    r = ctx.inputs
    decision = (
        r.decision
        if isinstance(r, Approve) and r.decision
        else Decision(kind="approve", actor="rules", reasons=["clean and under the auto-approval limit"])
    )
    key = _decided(ctx, decision)
    assert r.invoice.total is not None
    res = payment.pay(ctx.deps.conn, key, r.invoice.total, r.invoice.currency, r.usd_total, ctx.state.run_id)
    return Outcome(
        key=key,
        status=res.status,
        decision=decision,
        findings=r.findings,
        run_id=ctx.state.run_id,
        amount_paid=res.amount if res.status == Status.PAID else None,
        invoice=r.invoice,
    )


@g.step
async def reject(ctx: StepContext[State, Deps, Reject]) -> Outcome:
    """Log a rejection with its reasons and the offending findings (FR-4.2)."""
    r = ctx.inputs
    decision = r.decision or Decision(kind="reject", actor="rules")
    key = _decided(ctx, decision)
    db.record(
        ctx.deps.conn, key, EventType.REJECTED, actor=decision.actor, run_id=ctx.state.run_id,
        payload={
            "reasons": decision.reasons, "rule_ids": decision.cited_rule_ids,
            # D4: name the offending lines so the vendor can reissue rather than being short-paid.
            "bad_lines": sorted({str(f.evidence.get("item") or f.evidence.get("sku")) for f in r.findings
                                 if f.severity == "hard" and (f.evidence.get("item") or f.evidence.get("sku"))}),
        },
        status=Status.REJECTED,
    )  # fmt: skip
    return Outcome(
        key=key,
        status=Status.REJECTED,
        decision=decision,
        findings=r.findings,
        run_id=ctx.state.run_id,
        invoice=r.invoice,
    )


@g.step
async def escalate(ctx: StepContext[State, Deps, HumanReview]) -> Outcome:
    """Send to the human inbox."""
    r = ctx.inputs
    decision = Decision(kind="escalate", actor="approval", reasons=[r.reason], label=r.label)
    key = _decided(ctx, decision)
    db.enqueue_inbox(ctx.deps.conn, key, reason=r.reason, label=r.label, run_id=ctx.state.run_id, actor="approval")
    return Outcome(
        key=key,
        status=Status.ESCALATED,
        decision=decision,
        findings=r.findings,
        run_id=ctx.state.run_id,
        invoice=r.invoice,
    )


@g.step
async def load_failed(ctx: StepContext[State, Deps, LoadFailed]) -> Outcome:
    """Reject a file that could not be read."""
    key = InvoiceKey("(unreadable)", ctx.state.path.name)
    f = Finding(rule_id="LOAD_FAILED", severity="hard", message=ctx.inputs.reason)
    decision = Decision(kind="reject", actor="intake", reasons=[ctx.inputs.reason], cited_rule_ids=["LOAD_FAILED"])
    db.record(
        ctx.deps.conn, key, EventType.REJECTED, actor="intake", run_id=ctx.state.run_id,
        payload=decision.model_dump(), status=Status.REJECTED, source_path=str(ctx.state.path),
    )  # fmt: skip
    return Outcome(key=key, status=Status.REJECTED, decision=decision, findings=[f], run_id=ctx.state.run_id)


g.add(
    g.edge_from(g.start_node).to(load_file),
    g.edge_from(load_file).to(
        g.decision().branch(g.match(Loaded).to(extract)).branch(g.match(LoadFailed).to(load_failed))
    ),
    g.edge_from(extract).to(reconcile_step),
    g.edge_from(reconcile_step).to(
        g.decision().branch(g.match(Reconciled).to(validate)).branch(g.match(Retry).to(retry))
    ),
    g.edge_from(retry).to(extract),
    g.edge_from(validate).to(
        g.decision()
        .branch(g.match(AutoApprove).to(pay))
        .branch(g.match(VpReview).to(vp_propose))
        .branch(g.match(HumanReview).to(escalate))
        .branch(g.match(Reject).to(reject))
    ),
    g.edge_from(vp_propose).to(critique),
    g.edge_from(critique).to(
        g.decision()
        .branch(g.match(Approve).to(pay))
        .branch(g.match(Reject).to(reject))
        .branch(g.match(Objected).to(vp_propose))
        .branch(g.match(HumanReview).to(escalate))
    ),
    g.edge_from(pay, reject, escalate, load_failed).to(g.end_node),
)
graph = g.build()


async def process(path: Path, settings: Settings, conn: sqlite3.Connection, run_id: str | None = None) -> Outcome:
    """Run one file through the whole graph."""
    run_id = run_id or new_run_id()
    state = State(path=path, run_id=run_id)
    deps = Deps(conn, settings, Tracer(settings.runs_dir, run_id))
    outcome = await graph.run(state=state, deps=deps, inputs=path)
    return outcome.model_copy(update={"source_path": str(path)})


def process_sync(path: Path, settings: Settings, conn: sqlite3.Connection, run_id: str | None = None) -> Outcome:
    """Synchronous wrapper for the CLI and Streamlit."""
    return asyncio.run(process(path, settings, conn, run_id))


def mermaid() -> str:
    """The graph as a Mermaid state diagram."""
    return graph.render(title="Invoice processing")
