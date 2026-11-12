"""Write the hand-made golden outputs used by --offline (A4). Values are copied as written on each document.

Run once, then ``scripts/stamp_goldens.py`` fills in the file hashes. Re-running overwrites.
"""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
G = ROOT / "fixtures" / "golden"


def L(
    item: str, qty: str, price: str | None = None, amount: str | None = None, note: str | None = None
) -> dict[str, Any]:
    """One raw line."""
    return {"item": item, "quantity": qty, "unit_price": price, "amount": amount, "note": note}


SUMMIT = dict(
    vendor="Summit Manufacturing Co.", invoice_number="INV-1011", invoice_date="2026-01-20", due_date="2026-02-20"
)
SUMMIT_LINES = [L("WidgetA", "6", "$250.00", "$1,500.00"), L("WidgetB", "3", "$500.00", "$1,500.00")]
QUICKSHIP = dict(
    vendor="QuickShip Distributers",
    invoice_number="INV 1012",
    invoice_date="26-Jan-2O26",
    due_date="25-Feb-2026",
    lines=[
        L("Widget A", "12", "$250", "$3,000.00"),
        L("WidgetB", "7", "$500", "$3,500.O0"),
        L("Gadget X", "4", "$750", "$3,000.00"),
    ],
    subtotal="$9,500.00",
    tax="$475.00",
    total="$9,975.00",
    payment_terms="Net 30",
    notes="Ref PO-20260115. Deliver to warehouse dock B. Contact Jim at ext 4421 with questions.",
)
ATLAS_LINES = [
    L("WidgetA", "15", "250.00", "3750.00"),
    L("WidgetB", "10", "500.00", "5000.00"),
    L("GadgetX", "5", "750.00", "3750.00"),
    L("WidgetA", "5", "240.00", "1200.00", "Volume discount"),
    L("WidgetB", "8", "480.00", "3840.00", "Volume discount"),
    L("GadgetX", "3", "750.00", "2250.00", "Expedited"),
    L("WidgetA", "2", "250.00", "500.00", "Replacement"),
    L("GadgetX", "1", "750.00", "750.00", "Sample"),
]

EXTRACT: dict[str, dict[str, Any]] = {
    "invoice_1001.txt": dict(
        vendor="Widgets Inc.",
        invoice_number="INV-1001",
        invoice_date="2026-01-15",
        due_date="2026-02-01",
        lines=[L("WidgetA", "10", "$250.00"), L("WidgetB", "5", "$500.00")],
        subtotal="$5,000.00",
        tax="$0.00",
        total="$5,000.00",
        payment_terms="Net 15",
    ),
    "invoice_1002.txt": dict(
        vendor="Gadgets Co.",
        invoice_number="1002",
        invoice_date="Jan 30 2026",
        due_date="2026-01-30",
        lines=[L("GadgetX", "20", "$750")],
        total="$15,000.00",
        payment_terms="Net 30",
    ),
    "invoice_1003.txt": dict(
        vendor="Fraudster LLC",
        invoice_number="INV-1003",
        invoice_date="2026-01-20",
        due_date="yesterday",
        lines=[L("FakeItem", "100", "$1,000.00")],
        total="$100,000.00",
        payment_terms="Immediate",
        notes="URGENT - Pay immediately to avoid penalties!!! Wire transfer preferred.",
    ),
    "invoice_1004.json": dict(
        vendor="Precision Parts Ltd.",
        vendor_address="742 Evergreen Terrace, Springfield, IL 62704",
        invoice_number="INV-1004",
        invoice_date="2026-01-22",
        due_date="2026-02-22",
        currency="USD",
        lines=[L("WidgetA", "3", "250.00"), L("WidgetB", "2", "500.00")],
        subtotal="1750.00",
        tax="140.00",
        total="1890.00",
        payment_terms="Net 30",
    ),
    "invoice_1004_revised.json": dict(
        vendor="Precision Parts Ltd.",
        vendor_address="742 Evergreen Terrace, Springfield, IL 62704",
        invoice_number="INV-1004",
        revision="R1",
        invoice_date="2026-01-22",
        due_date="2026-02-22",
        currency="USD",
        lines=[L("WidgetA", "3", "250.00"), L("WidgetB", "2", "500.00"), L("GadgetX", "5", "750.00")],
        subtotal="5500.00",
        tax="440.00",
        total="5940.00",
        payment_terms="Net 30",
        notes="Revised invoice - additional items added per PO amendment",
    ),
    "invoice_1005.json": dict(
        vendor="Global Supply Chain Partners",
        vendor_address="1600 Pennsylvania Ave, Washington, DC 20500",
        invoice_number="INV-1005",
        invoice_date="2026-01-18",
        due_date="2026-03-18",
        currency="USD",
        lines=[L("WidgetA", "14", "250.00"), L("GadgetX", "8", "750.00"), L("WidgetB", "10", "500.00")],
        subtotal="14500.00",
        tax="725.00",
        total="15225.00",
        payment_terms="Net 60",
    ),
    "invoice_1006.csv": dict(
        vendor="Acme Industrial Supplies",
        invoice_number="INV-1006",
        invoice_date="2026-01-25",
        due_date="2026-02-10",
        lines=[L("WidgetA", "5", "250.00"), L("WidgetB", "3", "500.00")],
        subtotal="2750.00",
        tax="0.00",
        total="2750.00",
        payment_terms="Net 15",
    ),
    "invoice_1007.csv": dict(
        vendor="MegaWidgets Corp",
        invoice_number="INV-1007",
        invoice_date="01/28/2026",
        due_date="02/28/2026",
        lines=[
            L("WidgetA", "20", "250.00", "5000.00"),
            L("WidgetB", "15", "500.00", "7500.00"),
            L("GadgetX", "3", "750.00", "2250.00"),
        ],
        subtotal="14750.00",
        tax="885.00",
        total="15525.00",
    ),
    "invoice_1008.txt": dict(
        vendor="NoProd Industries",
        invoice_number="INV-1008",
        invoice_date="2026-01-10",
        due_date="2026-01-20",
        lines=[L("SuperGizmo", "12", "$400.00"), L("MegaSprocket", "6", "$850.00")],
        total="$9,900.00",
    ),
    "invoice_1009.json": dict(
        vendor="",
        vendor_address=None,
        invoice_number="INV-1009",
        invoice_date="2026-01-15",
        due_date=None,
        currency="USD",
        lines=[L("WidgetA", "-5", "250.00"), L("WidgetB", "2", "500.00")],
        subtotal="1000.00",
        tax="0.00",
        total="-250.00",
        payment_terms="",
    ),
    "invoice_1010.txt": dict(
        vendor="Consolidated Materials Group",
        invoice_number="INV-1010",
        invoice_date="January 27, 2026",
        due_date="February 26, 2026",
        lines=[
            L("WidgetA", "8", "$250.00", "$2,000.00"),
            L("WidgetB", "4", "$500.00", "$2,000.00"),
            L("GadgetX", "2", "$750.00", "$1,500.00"),
            L("WidgetA (rush order)", "4", "$300.00", "$1,200.00"),
        ],
        subtotal="$6,700.00",
        tax="$335.00",
        shipping="$150.00",
        total="$7,185.00",
        payment_terms="Net 30",
    ),
    "invoice_1011.txt": dict(
        **SUMMIT, lines=SUMMIT_LINES, subtotal="$3,000.00", tax="$0.00", total="$3,000.00", payment_terms="Net 30"
    ),
    "invoice_1011.pdf": dict(**SUMMIT, lines=SUMMIT_LINES, total="$3,000.00"),
    "invoice_1012.txt": QUICKSHIP,
    "invoice_1012.pdf": QUICKSHIP,
    "invoice_1013.json": dict(
        vendor="Atlas Industrial Supply",
        vendor_address="500 Commerce Blvd, Detroit, MI 48201",
        invoice_number="INV-1013",
        invoice_date="2026-01-24",
        due_date="2026-03-24",
        currency="USD",
        lines=ATLAS_LINES,
        subtotal="21040.00",
        tax="1472.80",
        total="22562.80",
        payment_terms="Net 60",
    ),
    "invoice_1013.pdf": dict(
        vendor="Atlas Industrial Supply",
        invoice_number="INV-1013",
        invoice_date="2026-01-24",
        due_date="2026-03-24",
        lines=[
            {**ln, "unit_price": f"${float(ln['unit_price']):,.2f}", "amount": f"${float(ln['amount']):,.2f}"}
            for ln in ATLAS_LINES
        ],
        subtotal="$21,040.00",
        tax="$1,472.80",
        total="$22,562.80",
        payment_terms="Net 60",
    ),
    "invoice_1014.xml": dict(
        vendor="TechParts International",
        invoice_number="INV-1014",
        invoice_date="2026-01-26",
        due_date="2026-02-26",
        currency="EUR",
        lines=[L("WidgetA", "4", "225.00"), L("WidgetB", "6", "475.00")],
        subtotal="3750.00",
        tax="375.00",
        total="4125.00",
        payment_terms="Net 30",
    ),
    "invoice_1015.csv": dict(
        vendor="Reliable Components Inc.",
        invoice_number="INV-1015",
        invoice_date="2026-01-29",
        due_date="2026-02-28",
        lines=[
            L("WidgetA", "10", "250.00", "2500.00"),
            L("WidgetB", "5", "500.00", "2500.00"),
            L("GadgetX", "2", "750.00", "1500.00"),
        ],
        subtotal="6500.00",
        tax="0.00",
        total="6500.00",
    ),
    "invoice_1016.json": dict(
        vendor="Widgets Inc.",
        vendor_address="100 Main St, Chicago, IL 60601",
        invoice_number="INV-1016",
        invoice_date="2026-01-27",
        due_date="2026-02-27",
        currency="USD",
        lines=[
            L("WidgetA", "4", "250.00", "1000.00"),
            L("WidgetB", "2", "500.00", "1000.00"),
            L("WidgetC", "3", "350.00", "1050.00"),
        ],
        subtotal="3050.00",
        tax="183.00",
        total="3233.00",
        payment_terms="Net 30",
    ),
}

# D28: fixed VP-tier outcomes. 1001 and 1010 are approved; on 1012 the critic objects twice → inbox.
AGREE = {"agrees": True, "objections": []}
REVIEW: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {
    "invoice_1001.txt": (
        [
            {
                "decision": "approve",
                "reasons": [
                    "Due date is two days later than Net 15 implies; a later due date "
                    "favours Acme and the goods and prices match the catalog."
                ],
                "cited_rule_ids": ["DUE_TERMS_MISMATCH"],
            }
        ],
        [AGREE],
    ),
    "invoice_1010.txt": (
        [
            {
                "decision": "approve",
                "reasons": [
                    "The $50/unit premium is on a line the vendor labels 'rush order'; "
                    "the surcharge is itemised and the rest of the invoice is at catalog."
                ],
                "cited_rule_ids": ["PRICE_OVER_CATALOG"],
            }
        ],
        [AGREE],
    ),
}
VP_1012 = [
    {
        "decision": "approve",
        "reasons": [
            "QuickShip states it was formerly FastShip Ltd., a known vendor, and quotes "
            "PO-20260115; prices match the catalog."
        ],
        "cited_rule_ids": ["UNKNOWN_VENDOR", "NEAR_THRESHOLD"],
    },
    {
        "decision": "approve",
        "reasons": [
            "The rename note and PO reference are consistent with the FastShip "
            "relationship; the total is under the limit."
        ],
        "cited_rule_ids": ["UNKNOWN_VENDOR", "NEAR_THRESHOLD"],
    },
]
CRITIC_1012 = [
    {
        "agrees": False,
        "objections": [
            "The vendor name is not in the registry; the rename claim comes only from the "
            "invoice itself and is unverified.",
            "The total sits $25 under the auto-approval limit.",
        ],
    },
    {
        "agrees": False,
        "objections": [
            "Paying a renamed payee on the invoice's own say-so is a known fraud pattern; "
            "remit-to details must be confirmed with FastShip through a known contact before payment."
        ],
    },
]
REVIEW["invoice_1012.txt"] = (VP_1012, CRITIC_1012)
REVIEW["invoice_1012.pdf"] = (VP_1012, CRITIC_1012)


def write(kind: str, name: str, body: dict[str, Any]) -> None:
    """Write one golden file."""
    d = G / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / (Path(name).stem + Path(name).suffix.replace(".", "_") + ".json")).write_text(
        json.dumps({"source": f"data/invoices/{name}", **body}, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Write every golden."""
    for old in G.rglob("*.json"):
        old.unlink()
    for name, out in EXTRACT.items():
        write("extract", name, {"output": out})
    for name, (vp, critic) in REVIEW.items():
        write("vp", name, {"attempts": vp})
        write("critic", name, {"attempts": critic})


if __name__ == "__main__":
    main()
