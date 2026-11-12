"""Loaders for TXT, CSV (both sample layouts), XML and text-layer PDF."""

import csv
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pdfplumber
from defusedxml.ElementTree import fromstring as safe_fromstring

from invoice_agents.loaders import ocr
from invoice_agents.models import RawDocument


def decode(data: bytes) -> str:
    """UTF-8 (BOM-tolerant, as Excel writes it), falling back to Latin-1."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def load_txt(path: Path, data: bytes, sha: str) -> RawDocument:
    """Plain text (including pasted emails): passed through for the extractor."""
    text = decode(data)
    if "\x00" in text:
        raise ValueError("binary content in a text file")
    return RawDocument(path=str(path), file_sha256=sha, format="txt", text=text)


def _kv_csv(rows: list[list[str]]) -> dict[str, Any]:
    """``field,value`` layout (1006): repeated item/quantity/unit_price keys form lines."""
    fields: dict[str, Any] = {}
    lines: list[dict[str, str]] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        k, v = row[0].strip().lower(), row[1].strip()
        if k == "item":
            lines.append({"item": v})
        elif k in ("quantity", "unit_price") and lines:
            lines[-1][k] = v
        elif k in fields and fields[k] != v:
            fields.setdefault("conflicting_keys", []).append(k)  # keep the first value; flag the clash
        else:
            fields.setdefault(k, v)
    fields["line_items"] = lines
    return fields


def _row_csv(rows: list[list[str]]) -> dict[str, Any]:
    """One row per line plus footer rows whose label sits in a value column (1007, 1015)."""
    header = [h.strip().title() for h in rows[0]]
    fields: dict[str, Any] = {"line_items": []}
    for row in rows[1:]:
        rec = dict(zip(header, (c.strip() for c in row), strict=False))
        if rec.get("Invoice Number") and rec.get("Item"):
            fields.setdefault("invoice_number", rec["Invoice Number"])
            fields.setdefault("vendor", rec.get("Vendor"))
            fields.setdefault("date", rec.get("Date"))
            fields.setdefault("due_date", rec.get("Due Date"))
            fields["line_items"].append(
                {
                    "item": rec.get("Item"),
                    "quantity": rec.get("Qty"),
                    "unit_price": rec.get("Unit Price"),
                    "line_total": rec.get("Line Total"),
                }
            )
        else:
            labelled = [c.strip() for c in row if c.strip()]
            if len(labelled) == 2:
                fields.setdefault("footer", []).append({"label": labelled[0], "value": labelled[1]})
    return fields


def load_csv(path: Path, data: bytes, sha: str) -> RawDocument:
    """CSV in either sample layout; unrecognised headers keep only the text."""
    text = decode(data)
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("no rows")
    head = [h.strip().lower() for h in rows[0]]
    if head[:2] == ["field", "value"]:
        fields = _kv_csv(rows)
    elif "invoice number" in head and "item" in head:
        fields = _row_csv(rows)
    else:
        fields = {}
    return RawDocument(path=str(path), file_sha256=sha, format="csv", text=text, fields=fields)


def _xml_to_obj(el: ET.Element) -> Any:
    kids = list(el)
    if not kids:
        return (el.text or "").strip()
    if len({c.tag for c in kids}) == 1 and len(kids) > 1:
        return [_xml_to_obj(c) for c in kids]
    return {c.tag: _xml_to_obj(c) for c in kids}


def load_xml(path: Path, data: bytes, sha: str) -> RawDocument:
    """XML parsed with defusedxml: DTDs and entities are refused in any encoding."""
    root = safe_fromstring(data, forbid_dtd=True)
    obj = _xml_to_obj(root)
    fields = obj if isinstance(obj, dict) else {"content": obj}
    return RawDocument(path=str(path), file_sha256=sha, format="xml", text=decode(data), fields=fields)


def load_pdf(path: Path, data: bytes, sha: str) -> RawDocument:
    """PDF via its text layer, keeping column layout so tables stay readable."""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [p.extract_text(layout=True) or "" for p in pdf.pages]
    text = "\n\n".join(t.rstrip() for t in pages).strip()
    if text:
        return RawDocument(path=str(path), file_sha256=sha, format="pdf", text=text)
    # No text layer: a scan. Local OCR first, page images kept for the vision model (D16).
    res = ocr.scan(data)
    if not res.images:
        raise ValueError("PDF has no pages")
    return RawDocument(
        path=str(path), file_sha256=sha, format="pdf", text=res.text, fields={"ocr": res.note}, page_images=res.images
    )
