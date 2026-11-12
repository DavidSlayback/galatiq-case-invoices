from pathlib import Path

from invoice_agents import eval as eval_mod
from invoice_agents.settings import Settings


def test_offline_eval_passes(tmp_path: Path):
    rows = eval_mod.run(Settings(model="offline", offline=True, runs_dir=tmp_path))
    assert len(rows) == 27
    assert [r.path for r in eval_mod.failures(rows)] == []


def test_eval_catches_a_wrong_expectation(tmp_path: Path):
    exp = {"data/invoices/invoice_1016.json": {"status": "paid", "requires": ["UNKNOWN_ITEM", "NOPE"]}}
    (row,) = eval_mod.run(Settings(model="offline", offline=True, runs_dir=tmp_path), exp)
    assert not row.passed and row.actual == "rejected" and row.missing == ["NOPE"]
