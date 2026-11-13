"""Vendor registry matching and a 0-100 risk score (D9, D10, FR-2.12).

Pure functions over the registry the rules already load, so the score is the
same wherever it is shown (findings, VP brief, inbox).
"""

from dataclasses import dataclass
from typing import Literal

from invoice_agents import identity
from invoice_agents.models import Finding

Match = Literal["exact", "alias", "lookalike", "unknown", "missing"]

# Signal weights. HIGH_RISK at 60 means two independent signals (or one strong one) are needed.
WEIGHTS = {"unknown": 40, "alias": 20, "lookalike": 60, "suspicious_address": 50, "urgency": 20}
HIGH_RISK = 60
LOOKALIKE_DISTANCE = 2


def distance(a: str, b: str) -> int:
    """Levenshtein edit distance."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass(frozen=True)
class VendorMatch:
    """How an invoice's vendor name relates to the registry."""

    kind: Match
    registered_as: str | None = None


def match(name: str | None, known: dict[str, str], aliases: dict[str, str]) -> VendorMatch:
    """Classify a vendor name against registry names and aliases (both keyed by :func:`identity.fold`, D38)."""
    n = identity.fold(name)
    if not n:
        return VendorMatch("missing")
    if n in known or n in aliases:
        # Equal only after NFKC folding (full-width or other look-alike code points): impersonation (B4).
        if identity.plain(name) != n:
            return VendorMatch("lookalike", known.get(n) or aliases[n])
        return VendorMatch("exact", known[n]) if n in known else VendorMatch("alias", aliases[n])
    # 'Widgets lnc.' (lower-case L for I) is one edit from 'Widgets Inc.'.
    near = [(distance(n, k), v) for k, v in known.items() if abs(len(k) - len(n)) <= LOOKALIKE_DISTANCE]
    best = min(near, default=None)
    if best and best[0] <= LOOKALIKE_DISTANCE:
        return VendorMatch("lookalike", best[1])
    return VendorMatch("unknown")


def score(m: VendorMatch, suspicious_address: bool, urgency: bool) -> tuple[int, list[str]]:
    """Risk score (capped at 100) and the signals behind it."""
    signals = [s for s, on in [
        (m.kind, m.kind in ("unknown", "alias", "lookalike")),
        ("suspicious_address", suspicious_address),
        ("urgency", urgency),
    ] if on]  # fmt: skip
    return min(100, sum(WEIGHTS[s] for s in signals)), signals


def master_changes(findings: list[Finding], vendor: str) -> list[dict[str, str]]:
    """Vendor-master changes a person can confirm from an invoice's findings (D50).

    A renamed vendor (VENDOR_RENAMED) can have its new name confirmed; new remittance
    details (BANK_DETAILS_CHANGED) can replace the bank reference on file. Look-alike
    names are never offered: confirming one would let an impostor in.
    """
    out: list[dict[str, str]] = []
    for f in findings:
        if f.rule_id == "VENDOR_RENAMED":
            out.append({"vendor": str(f.evidence["registered_as"]), "field": "confirmed_name",
                        "value": str(f.evidence["vendor"])})  # fmt: skip
        elif f.rule_id == "BANK_DETAILS_CHANGED":
            out.append({"vendor": vendor, "field": "bank_ref", "value": str(f.evidence["remit_to"])})
    return out
