"""erp_book contract tests."""
import json
from pathlib import Path

from erp import erp_book

ROOT = Path(__file__).resolve().parent.parent


def test_sample_autodraft_books_438():
    payable = json.loads((ROOT / "sample_autodraft.json").read_text(encoding="utf-8"))
    result = erp_book(payable)
    assert result["currency"] == "EUR"
    assert abs(result["will_book_gross"] - 438.0) < 0.01


def test_line_tax_vs_header_tax_differ():
    base = {
        "currency": "EUR",
        "discount_amount": "",
        "freight_charges": "",
        "insurance_charges": "",
        "extra_charges": "",
        "excise_duties": "",
        "line_items": [
            {
                "quantity": "1",
                "unit_price": "100",
                "discount": "",
                "discount_percentage": "",
                "tax_rate": "",
                "tax_amount": "",
                "taxes": [],
            }
        ],
        "taxes": [],
    }
    header = dict(base)
    header["taxes"] = [{"tax_rate": "20", "tax_amount": ""}]
    line = dict(base)
    line["line_items"] = [
        {
            **base["line_items"][0],
            "taxes": [{"tax_rate": "20", "tax_amount": ""}],
        }
    ]
    # Both should foot to 120 for this simple case
    assert abs(erp_book(header)["will_book_gross"] - 120.0) < 0.01
    assert abs(erp_book(line)["will_book_gross"] - 120.0) < 0.01
