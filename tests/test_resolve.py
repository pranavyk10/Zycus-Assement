"""Master resolver tests."""
from pathlib import Path

from src.resolve import MasterIndexes, MasterResolver

ROOT = Path(__file__).resolve().parent.parent


def test_supplier_vat_exact():
    idx = MasterIndexes.load(ROOT / "master_data")
    r = MasterResolver(idx)
    sid = r.match_supplier(name="", vat_id="DE209177122", address="")
    assert sid == "2845695"


def test_supplier_no_fabricate():
    idx = MasterIndexes.load(ROOT / "master_data")
    r = MasterResolver(idx)
    assert r.match_supplier(name="Totally Fake GmbH", vat_id="", address="") == ""


def test_payment_alias_and_days():
    idx = MasterIndexes.load(ROOT / "master_data")
    r = MasterResolver(idx)
    assert r.match_payment_term(text="Net 10", invoice_date="", due_date="") == "Net_10"
    assert (
        r.match_payment_term(text="", invoice_date="2026-02-02", due_date="2026-02-12") == "Net_10"
    )


def test_po_exact_or_blank():
    idx = MasterIndexes.load(ROOT / "master_data")
    r = MasterResolver(idx)
    assert r.match_po("PO-EE-2026-0044") == "PO-EE-2026-0044"
    assert r.match_po("PO-NOT-IN-MASTER") == ""


def test_tax_country_rate():
    idx = MasterIndexes.load(ROOT / "master_data")
    r = MasterResolver(idx)
    code = r.match_tax(tax_name="German VAT 19%", tax_rate="19", tax_type="VAT", country="DE")
    assert code == "DE_190_VAT"
