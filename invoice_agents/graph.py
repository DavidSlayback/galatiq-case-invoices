"""The processing graph: load → extract ⇄ reconcile → ledger → validate → VP ⇄ critic → settle / escalate.

Built with pydantic-graph (D11) and wiring only (D43): decisions live in the
stage modules (reconcile, ledger, rules, approval, settle). Business events go
through those modules or ``db``; steps add a trace line through ``Tracer``.
``mermaid()`` draws the full graph.
"""

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage
from pydantic_graph import GraphBuilder, StepContext

from invoice_agents import approval, db, fx, identity, ledger, payment, reconcile, rules, settle
from invoice_agents.agents import extractor, reviewers
from invoice_agents.approval import Approve, AutoApprove, HumanReview, Objected, Proposed, Reject, VpReview
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
from invoice_agents.normalize import NormalizeError
from invoice_agents.payment import Bank, mock_payment
from invoice_agents.settings import Settings
from invoice_agents.trace import Tracer, new_run_id

MAX_EXTRACT_RETRIES = 2  # D14


@dataclass
class Deps:
    """Run-wide services."""

    conn: sqlite3.Connection
    settings: Settings
    tracer: Tracer
    bank: Bank = mock_payment


@dataclass
class State:
    """Mutable per-invoice state carried between steps."""

    path: Path
    run_id: str
    doc: RawDocument | None = None
    invoice: Invoice | None = None
    key: InvoiceKey | None = None
    attempt: int = 0  # extraction attempt, 0-based; also the retry count
    feedback: str | None = None  # reconciliation problems for the next extraction attempt
    history: list[ModelMessage] = field(default_factory=list[ModelMessage])  # extractor messages, kept across retries
    findings: list[Finding] = field(default_factory=list[Finding])
    model_name: str = ""
    review_brief: str = ""  # the case the VP and critic both read, built once in round 0
    mismatches: list[str] = field(default_factory=list[str])
    amount_due: Decimal | None = None  # set when something was already paid on this invoice (A8, D46)
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
class DuplicateFound:
    """The ledger already holds this invoice (same or newer revision)."""

    invoice: Invoice
    why: dict[str, object]


@dataclass(frozen=True)
class ExtractFailed:
    """The model could not produce a usable extraction within its retry budget."""

    reason: str


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
    ctx.deps.tracer.log(
        "load",
        path=doc.path,
        format=doc.format,
        sha256=doc.file_sha256,
        pages=len(doc.page_images),
        ocr=doc.fields.get("ocr"),
    )
    return Loaded(doc)


@g.step
async def extract(ctx: StepContext[State, Deps, Loaded]) -> Extracted | ExtractFailed:
    """Ask the extraction agent for a typed invoice; a model that keeps failing goes to a human."""
    s = ctx.state
    try:
        result = await extractor.extract(ctx.inputs.doc, ctx.deps.settings, s.feedback, s.history, s.attempt)
    except (UnexpectedModelBehavior, NormalizeError) as e:
        ctx.deps.tracer.log("extract", attempt=s.attempt, error=str(e))
        return ExtractFailed(f"extraction failed: {e}")
    s.history, s.model_name = result.messages, result.model_name
    ctx.deps.tracer.log(
        "extract",
        attempt=s.attempt,
        model=result.model_name,
        tokens=result.tokens,
        invoice=result.invoice.model_dump(mode="json"),
    )
    return Extracted(result.invoice)


@g.step
async def reconcile_step(ctx: StepContext[State, Deps, Extracted]) -> Reconciled | Retry:
    """Check the arithmetic; retry extraction with the specific mismatch, at most twice (D14)."""
    s, inv = ctx.state, ctx.inputs.invoice
    problems = reconcile.mismatches(inv)
    doubts = reconcile.implausible_dates(inv)
    ctx.deps.tracer.log("reconcile", attempt=s.attempt, mismatches=problems, doubts=doubts)
    if (problems or doubts) and s.attempt < MAX_EXTRACT_RETRIES:
        return Retry("\n".join(problems + doubts))
    if problems:
        s.findings.append(reconcile.mismatch_finding(problems, attempts=s.attempt + 1))
    assert s.doc is not None
    s.invoice, s.key, s.mismatches = inv, identity.key_for(ctx.deps.conn, inv, s.doc.file_sha256), problems
    return Reconciled(inv)


@g.step
async def ledger_check(ctx: StepContext[State, Deps, Reconciled]) -> Reconciled | DuplicateFound:
    """Skip duplicates, supersede earlier revisions, and record receipt (D2, D25)."""
    s, d, inv = ctx.state, ctx.deps, ctx.inputs.invoice
    assert s.doc is not None and s.key is not None
    res = ledger.intake(
        d.conn, s.key, inv, run_id=s.run_id,
        source={"path": s.doc.path, "sha256": s.doc.file_sha256, "format": s.doc.format},
        extracted={"model": s.model_name, "attempts": s.attempt + 1, "mismatches": s.mismatches},
    )  # fmt: skip
    d.tracer.log("ledger", result=res.verdict)
    s.key, s.amount_due = res.key, res.amount_due
    s.findings += res.findings
    return DuplicateFound(inv, res.skipped) if res.skipped is not None else Reconciled(inv)


@g.step
async def duplicate(ctx: StepContext[State, Deps, DuplicateFound]) -> Outcome:
    """A copy of an invoice already on file: never processed or paid again."""
    s = ctx.state
    assert s.key is not None
    decision = Decision(kind="reject", actor="ledger", reasons=[json.dumps(ctx.inputs.why)])
    return Outcome(key=s.key, status=Status.DUPLICATE_SKIPPED, decision=decision, findings=s.findings,
                   run_id=s.run_id, invoice=ctx.inputs.invoice)  # fmt: skip


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
    s.findings += rules.validate(inv, d.conn, d.settings.as_of, s.doc.text if s.doc else "")
    s.findings += ledger.split_findings(d.conn, s.key, inv, approval.AUTO_LIMIT)
    db.record_findings(d.conn, s.key, s.run_id, s.findings)
    r = approval.route(inv, s.findings, fx.to_usd(inv.total, inv.currency, fx.rates(d.conn)), s.amount_due)
    if isinstance(r, HumanReview) and r.reason == approval.REVISION_AFTER_PAYMENT:
        db.record(d.conn, s.key, EventType.REVISION_AFTER_PAYMENT, actor="ledger", run_id=s.run_id,
                  payload={"amount_due": str(s.amount_due)})  # fmt: skip
    d.tracer.log("route", route=type(r).__name__, findings=[f.rule_id for f in s.findings])
    return r


@g.step
async def vp_propose(ctx: StepContext[State, Deps, VpReview | Objected]) -> Proposed | HumanReview:
    """The VP agent proposes approve or reject; on later rounds it answers the critic's objections."""
    s, r = ctx.state, ctx.inputs
    assert s.doc is not None
    round_ = r.round + 1 if isinstance(r, Objected) else 0
    if round_ == 0:
        s.review_brief = reviewers.case_brief(r.invoice, r.findings, r.usd_total)
    objections = list(r.objections) if isinstance(r, Objected) else []
    assert s.key is not None
    context = reviewers.ReviewContext(ctx.deps.conn, s.key)
    try:
        review = await reviewers.propose(
            s.doc, ctx.deps.settings, context, s.review_brief, objections, s.vp_history, round_
        )
    except AgentRunError as e:  # a failing model, or one stuck calling tools, goes to a person
        return HumanReview(r.invoice, r.findings, r.usd_total, reason=f"vp agent failed: {e}")
    p, s.vp_history = review.output, review.messages
    ctx.deps.tracer.log("vp_propose", round=round_, proposal=p.model_dump(), tools=review.tool_calls,
                        tokens=review.tokens)  # fmt: skip
    d = Decision(kind=p.decision, actor="vp_agent", reasons=p.reasons, cited_rule_ids=p.cited_rule_ids)
    return Proposed(r.invoice, r.findings, r.usd_total, decision=d, round=round_)


@g.step
async def critique(ctx: StepContext[State, Deps, Proposed]) -> Approve | Reject | Objected | HumanReview:
    """The critic checks the proposal; agreement goes to settlement, deadlock to a human."""
    s, r, d = ctx.state, ctx.inputs, ctx.deps
    assert s.doc is not None and r.decision is not None and s.key is not None
    known = {f.rule_id for f in r.findings}
    invented = [i for i in r.decision.cited_rule_ids if i not in known]
    if invented:  # checked in code: a citation must name a finding that exists
        verdict = reviewers.Critique(agrees=False, objections=[f"cited rule IDs not in the findings: {invented}"])
        critic_tools: list[dict[str, object]] = []
        critic_tokens = (0, 0)
    else:
        context = reviewers.ReviewContext(d.conn, s.key)
        try:
            review = await reviewers.critique(s.doc, d.settings, context, s.review_brief, r.decision, r.round)
        except AgentRunError as e:
            return HumanReview(r.invoice, r.findings, r.usd_total, reason=f"critic agent failed: {e}")
        verdict, critic_tools, critic_tokens = review.output, review.tool_calls, review.tokens
    d.tracer.log("critique", round=r.round, verdict=verdict.model_dump(), tools=critic_tools, tokens=critic_tokens)
    if verdict.agrees:  # settling applies the guardrail, so an agreed approval with a hard finding still rejects
        if r.decision.kind == "approve":
            return Approve(r.invoice, r.findings, r.usd_total, decision=r.decision)
        return Reject(r.invoice, r.findings, r.usd_total, decision=r.decision)
    if r.round + 1 < approval.MAX_REVIEW_ROUNDS:
        return Objected(r.invoice, r.findings, r.usd_total, objections=tuple(verdict.objections), round=r.round)
    vp = f"VP proposed {r.decision.kind}: " + " ".join(r.decision.reasons)
    critic = "Critic objected: " + " ".join(verdict.objections)
    return HumanReview(r.invoice, r.findings, r.usd_total, reason="vp_critic_disagree", detail=(vp, critic))


@g.step
async def settle_step(ctx: StepContext[State, Deps, AutoApprove | Approve | Reject]) -> Outcome:
    """Pay an approval or log a rejection, through the same settlement a person's decision uses."""
    r, st = ctx.inputs, ctx.state
    assert st.key is not None
    if isinstance(r, AutoApprove):
        decision = Decision(kind="approve", actor="rules", reasons=["clean and under the auto-approval limit"])
    else:
        decision = r.decision or Decision(kind=("approve" if isinstance(r, Approve) else "reject"), actor="rules")
    done = settle.settle(
        ctx.deps.conn, st.key, decision, findings=r.findings, total=r.invoice.total, currency=r.invoice.currency,
        usd_total=r.usd_total, run_id=st.run_id, bank=ctx.deps.bank,
    )  # fmt: skip
    return Outcome(key=st.key, status=done.status, decision=done.decision, findings=r.findings, run_id=st.run_id,
                   amount_paid=done.amount_paid, invoice=r.invoice)  # fmt: skip


@g.step
async def escalate(ctx: StepContext[State, Deps, HumanReview]) -> Outcome:
    """Send to the human inbox."""
    r = ctx.inputs
    decision = Decision(kind="escalate", actor="approval", reasons=[r.reason, *r.detail], label=r.label)
    key = ctx.state.key
    assert key is not None
    db.record(ctx.deps.conn, key, EventType.DECIDED, actor=decision.actor, run_id=ctx.state.run_id,
              payload=decision.model_dump())  # fmt: skip
    db.enqueue_inbox(
        ctx.deps.conn, key, reason=r.reason, label=r.label, run_id=ctx.state.run_id, actor="approval",
        amount_due=ctx.state.amount_due,
    )  # fmt: skip
    return Outcome(
        key=key,
        status=Status.ESCALATED,
        decision=decision,
        findings=r.findings,
        run_id=ctx.state.run_id,
        invoice=r.invoice,
    )


@g.step
async def extract_failed(ctx: StepContext[State, Deps, ExtractFailed]) -> Outcome:
    """Send a document the model could not read to a human, never to payment."""
    key = InvoiceKey("(unextracted)", ctx.state.path.name)
    reason = ctx.inputs.reason
    db.enqueue_inbox(
        ctx.deps.conn, key, reason="extraction_failed", run_id=ctx.state.run_id, actor="extractor",
        payload={"error": reason, "path": str(ctx.state.path)},
    )  # fmt: skip
    decision = Decision(kind="escalate", actor="extractor", reasons=[reason])
    return Outcome(key=key, status=Status.ESCALATED, decision=decision, run_id=ctx.state.run_id)


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
    g.edge_from(extract).to(
        g.decision().branch(g.match(Extracted).to(reconcile_step)).branch(g.match(ExtractFailed).to(extract_failed))
    ),
    g.edge_from(reconcile_step).to(
        g.decision().branch(g.match(Reconciled).to(ledger_check)).branch(g.match(Retry).to(retry))
    ),
    g.edge_from(ledger_check).to(
        g.decision().branch(g.match(Reconciled).to(validate)).branch(g.match(DuplicateFound).to(duplicate))
    ),
    g.edge_from(retry).to(extract),
    g.edge_from(validate).to(
        g.decision()
        .branch(g.match(AutoApprove).to(settle_step))
        .branch(g.match(VpReview).to(vp_propose))
        .branch(g.match(HumanReview).to(escalate))
        .branch(g.match(Reject).to(settle_step))
    ),
    g.edge_from(vp_propose).to(
        g.decision().branch(g.match(Proposed).to(critique)).branch(g.match(HumanReview).to(escalate))
    ),
    g.edge_from(critique).to(
        g.decision()
        .branch(g.match(Approve).to(settle_step))
        .branch(g.match(Reject).to(settle_step))
        .branch(g.match(Objected).to(vp_propose))
        .branch(g.match(HumanReview).to(escalate))
    ),
    g.edge_from(settle_step, escalate, load_failed, extract_failed, duplicate).to(g.end_node),
)
graph = g.build()


async def process(
    path: Path, settings: Settings, conn: sqlite3.Connection, run_id: str | None = None, bank: Bank = mock_payment
) -> Outcome:
    """Run one file through the whole graph; ``bank`` is the payment adapter.

    First surfaces any payment a dead process left pending (:func:`payment.sweep_unconfirmed`).
    Every file ends in an Outcome; errors outside the graph's handled cases (a missing offline
    golden, a database error) propagate.
    """
    run_id = run_id or new_run_id()
    payment.sweep_unconfirmed(conn, run_id)
    ledger.sweep_unsettled_decisions(conn, run_id)
    state = State(path=path, run_id=run_id)
    deps = Deps(conn, settings, Tracer(settings.runs_dir, run_id), bank)
    outcome = await graph.run(state=state, deps=deps, inputs=path)
    return outcome.model_copy(update={"source_path": str(path)})


def process_sync(
    path: Path, settings: Settings, conn: sqlite3.Connection, run_id: str | None = None, bank: Bank = mock_payment
) -> Outcome:
    """Synchronous wrapper for the CLI and Streamlit."""
    return asyncio.run(process(path, settings, conn, run_id, bank))


def mermaid() -> str:
    """The graph as a Mermaid state diagram."""
    return graph.render(title="Invoice processing")
