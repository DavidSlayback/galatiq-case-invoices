from pathlib import Path

import pytest

from invoice_agents.loaders import LoadError, load
from tests.conftest import INVOICES

SAMPLES = sorted(p for p in INVOICES.iterdir() if p.is_file())


def test_sample_set_is_twenty_files():
    assert len(SAMPLES) == 20


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_every_sample_loads(path: Path):
    doc = load(path)
    assert doc.text.strip() and len(doc.file_sha256) == 64
    number = path.stem.split("_")[1]
    assert number in doc.text


def test_csv_layouts():
    kv = load(INVOICES / "invoice_1006.csv").fields
    assert kv["invoice_number"] == "INV-1006" and len(kv["line_items"]) == 2
    assert kv["line_items"][1] == {"item": "WidgetB", "quantity": "3", "unit_price": "500.00"}
    rows = load(INVOICES / "invoice_1007.csv").fields
    assert len(rows["line_items"]) == 3 and rows["vendor"] == "MegaWidgets Corp"
    assert rows["footer"][-1] == {"label": "Total:", "value": "15525.00"}
    assert len(load(INVOICES / "invoice_1015.csv").fields["line_items"]) == 3


def test_xml_fields():
    f = load(INVOICES / "invoice_1014.xml").fields
    assert f["header"]["currency"] == "EUR" and len(f["line_items"]) == 2


def test_pdf_text_layer_keeps_table():
    doc = load(INVOICES / "invoice_1013.pdf")
    assert "Volume discount" in doc.text and "22,562.80" in doc.text


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("empty.txt", b"   \n"),
        ("bin.txt", b"abc\x00def"),
        ("bad.json", b"{not json"),
        ("list.json", b"[1, 2]"),
        ("bad.xml", b"<invoice><x></invoice>"),
        ("bomb.xml", b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>'),
        ("bad.pdf", b"%PDF-1.4 garbage"),
        ("doc.docx", b"PK\x03\x04"),
        ("noext", b"hello"),
    ],
)
def test_malformed_inputs_raise_load_error(tmp_path: Path, name: str, content: bytes):
    p = tmp_path / name
    p.write_bytes(content)
    with pytest.raises(LoadError):
        load(p)


def test_missing_file(tmp_path: Path):
    with pytest.raises(LoadError):
        load(tmp_path / "nope.txt")


def test_utf16_xml_entity_is_refused(tmp_path: Path):
    p = tmp_path / "u16.xml"
    p.write_bytes('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "b">]><r>&a;</r>'.encode("utf-16"))
    with pytest.raises(LoadError):
        load(p)


def test_fifo_is_refused_without_blocking(tmp_path: Path):
    import os

    p = tmp_path / "pipe.txt"
    os.mkfifo(p)
    with pytest.raises(LoadError, match="regular file"):
        load(p)


def test_bom_csv_still_parses(tmp_path: Path):
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbf" + (INVOICES / "invoice_1006.csv").read_bytes())
    assert len(load(p).fields["line_items"]) == 2


def test_kv_csv_keys_are_case_insensitive_and_clashes_flagged(tmp_path: Path):
    p = tmp_path / "kv.csv"
    p.write_text("Field,Value\nVendor,A\nvendor,B\nItem,WidgetA\nQuantity,2\n")
    f = load(p).fields
    assert f["vendor"] == "A" and f["conflicting_keys"] == ["vendor"]
    assert f["line_items"] == [{"item": "WidgetA", "quantity": "2"}]


def test_row_csv_skips_rows_without_an_item(tmp_path: Path):
    p = tmp_path / "rows.csv"
    p.write_text("Invoice Number,Vendor,Item,Qty\nINV-1,V\nINV-1,V,WidgetA,3\n")
    assert load(p).fields["line_items"] == [
        {"item": "WidgetA", "quantity": "3", "unit_price": None, "line_total": None}
    ]


@pytest.mark.parametrize("content", [b'{"a": NaN}', b'{"a": Infinity}'])
def test_json_nonstandard_constants_rejected(tmp_path: Path, content: bytes):
    p = tmp_path / "c.json"
    p.write_bytes(content)
    with pytest.raises(LoadError):
        load(p)


def test_json_with_bom_loads(tmp_path: Path):
    p = tmp_path / "bom.json"
    p.write_bytes(b'\xef\xbb\xbf{"invoice_number": "INV-1"}')
    assert load(p).fields["invoice_number"] == "INV-1"
