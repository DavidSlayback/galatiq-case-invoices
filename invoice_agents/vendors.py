"""Vendor registry matching and a 0-100 risk score (D9, D10, FR-2.12).

Pure functions over the registry the rules already load, so the score is the
same wherever it is shown (findings, VP brief, inbox).
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Match = Literal["exact", "alias", "lookalike", "unknown", "missing"]

# Signal weights. HIGH_RISK at 60 means two independent signals (or one strong one) are needed.
WEIGHTS = {"unknown": 40, "alias": 20, "lookalike": 60, "suspicious_address": 50, "urgency": 20}
HIGH_RISK = 60
LOOKALIKE_DISTANCE = 2


def norm(name: str | None) -> str:
    """Comparison form: NFKC (folds look-alike Unicode forms), lower case, single spaces."""
    s = unicodedata.normalize("NFKC", name or "")
    return re.sub(r"\s+", " ", s.strip().lower())


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
    """Classify a vendor name against registry names and aliases (both keyed by ``norm``)."""
    n = norm(name)
    if not n:
        return VendorMatch("missing")
    if n in known:
        return VendorMatch("exact", known[n])
    if n in aliases:
        return VendorMatch("alias", aliases[n])
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
