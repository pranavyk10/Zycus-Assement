output/"""Output envelope shape tests."""
from src.schema import empty_payable, merge_payable, output_envelope


def test_envelope_keys():
    env = output_envelope("X.pdf", payables=[empty_payable()], declined=[])
    assert set(env.keys()) == {"file", "payables", "declined"}
    assert env["file"] == "X.pdf"


def test_merge_preserves_grounded_fields():
    p = merge_payable(
        {
            "invoice_number": "1",
            "currency": "EUR",
            "gross_total": "10.00",
            "supplier": {"name": "Acme", "vat_id": "X"},
            "line_items": [{"description": "A", "quantity": "1", "unit_price": "10.00"}],
        }
    )
    assert p["invoice_number"] == "1"
    assert p["supplier"]["name"] == "Acme"
    assert p["supplier"]["supplier_id"] == ""
    assert len(p["line_items"]) == 1
    assert p["buyer"]["company_code"] == ""
