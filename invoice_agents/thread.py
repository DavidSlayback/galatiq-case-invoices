"""A run's trace as a readable conversation between the agents and the code (shown in the dashboard).

The trace (``runs/<run_id>.jsonl``) records every stage; this turns it into who said
what, in order: the extractor reading the file, the code checking it, the VP proposing
and looking things up, the critic agreeing or objecting. Pure, so it is tested directly.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Speaker = Literal["extractor", "code", "vp", "critic"]

ROUTES = {
    "AutoApprove": "pay it automatically",
    "VpReview": "send it to the VP agent",
    "HumanReview": "send it to a person",
    "Reject": "reject it",
}
LEDGER = {
    "New": "New invoice; recorded in the ledger.",
    "Duplicate": "Already on file: this copy is skipped.",
    "Stale": "An older revision than the one on file: skipped.",
    "Revision": "A newer revision of an invoice on file: it supersedes the original.",
    "Conflict": "Same number as an invoice on file but different content: flagged as possible fraud.",
}


@dataclass(frozen=True)
class Turn:
    """One message in the thread: who, what they concluded, and the supporting detail."""

    speaker: Speaker
    text: str
    details: list[str] = field(default_factory=list[str])


def _lookup(call: dict[str, Any]) -> str:
    """One tool call in plain words, with the part of its result that mattered."""
    r = call.get("result") or {}
    if call["tool"] == "vendor_history":
        paid = ", ".join(f"{a} {c}" for c, a in (r.get("total_paid") or {}).items()) or "nothing yet"
        return f"Looked up the vendor's history: {r.get('note', 'no result')}; paid so far: {paid}."
    if call["tool"] == "catalog_item":
        sku = call["args"].get("sku", "?")
        if not r.get("in_catalog", True):
            return f"Looked up {sku} in the catalog: not in the catalog."
        return f"Looked up {sku} in the catalog: {r.get('unit_price')} each, {r.get('stock')} in stock."
    return f"Called {call['tool']}({call.get('args')})."


def turns(trace: list[dict[str, Any]]) -> list[Turn]:
    """The conversation for one run, oldest first. Stages without a story (file loading) are skipped."""
    out: list[Turn] = []
    for t in trace:
        node = t.get("node")
        if node == "extract":
            if t.get("error"):
                out.append(Turn("extractor", f"Could not produce a usable reading of the file: {t['error']}"))
                continue
            inv = t.get("invoice") or {}
            again = f" (attempt {t['attempt'] + 1})" if t.get("attempt") else ""
            who = f"{inv.get('vendor') or 'no vendor'}, {inv.get('invoice_number') or 'no number'}"
            text = (
                f"Read the invoice{again}: {who}, total {inv.get('total') or '?'} {inv.get('currency') or ''},"
                f" {len(inv.get('lines') or [])} line(s)."
            )
            out.append(Turn("extractor", text, [f"Model: {t.get('model')}"] if t.get("model") else []))
        elif node == "reconcile":
            problems = [*(t.get("mismatches") or []), *(t.get("doubts") or [])]
            text = "The arithmetic checks out." if not problems else "These don't add up; asking the extractor again."
            out.append(Turn("code", text, problems))
        elif node == "ledger":
            out.append(Turn("code", LEDGER.get(str(t.get("result")), f"Ledger check: {t.get('result')}.")))
        elif node == "route":
            flags = t.get("findings") or []
            route = ROUTES.get(str(t.get("route")), str(t.get("route")))
            out.append(Turn("code", f"Rules raised {', '.join(flags) or 'no flags'}. Decision: {route}."))
        elif node == "vp_propose":
            p = t.get("proposal") or {}
            cites = f" Cites {', '.join(p['cited_rule_ids'])}." if p.get("cited_rule_ids") else ""
            text = f"I propose to **{p.get('decision', '?')}**.{cites}"
            out.append(Turn("vp", text, [*map(_lookup, t.get("tools") or []), *(p.get("reasons") or [])]))
        elif node == "critique":
            v = t.get("verdict") or {}
            text = "I agree." if v.get("agrees") else "I object."
            out.append(Turn("critic", text, [*map(_lookup, t.get("tools") or []), *(v.get("objections") or [])]))
    return out
