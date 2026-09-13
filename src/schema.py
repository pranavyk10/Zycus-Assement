"""Autodraft schema helpers and output envelope."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def empty_tax() -> dict[str, str]:
    return {
        "tax_type": "",
        "tax_name": "",
        "tax_rate": "",
        "tax_amount": "",
        "tax_type_code": "",
    }


def empty_line_item() -> dict[str, Any]:
    return {
        "description": "",
        "item_type": "SERVICE",
        "uom": "",
        "quantity": "",
        "unit_price": "",
        "total": "",
        "discount": "",
        "discount_percentage": "",
        "tax_rate": "",
        "tax_amount": "",
        "taxes": [],
    }


def empty_payable() -> dict[str, Any]:
    return {
        "invoice_number": "",
        "invoice_date": "",
        "due_date": "",
        "invoice_type": "INVOICE",
        "currency": "",
        "supplier": {
            "name": "",
            "supplier_id": "",
            "address": "",
            "vat_id": "",
        },
        "buyer": {
            "company_code": "",
            "business_unit_code": "",
            "location_code": "",
        },
        "payment_term_id": "",
        "po_number": "",
        "po_id": "",
        "gross_total": "",
        "subtotal": "",
        "total_tax_amount": "",
        "discount_amount": "",
        "freight_charges": "",
        "insurance_charges": "",
        "extra_charges": "",
        "excise_duties": "",
        "taxes": [],
        "line_items": [],
    }


def output_envelope(file_name: str, payables: list[dict] | None = None, declined: list[dict] | None = None) -> dict:
    return {
        "file": file_name,
        "payables": payables or [],
        "declined": declined or [],
    }


def merge_payable(partial: dict[str, Any]) -> dict[str, Any]:
    """Fill missing keys from the empty template without inventing values."""
    base = empty_payable()
    if not isinstance(partial, dict):
        return base

    for key in base:
        if key not in partial or partial[key] is None:
            continue
        if key == "supplier" and isinstance(partial[key], dict):
            for sk in base["supplier"]:
                if sk in partial["supplier"] and partial["supplier"][sk] is not None:
                    base["supplier"][sk] = str(partial["supplier"][sk])
        elif key == "buyer" and isinstance(partial[key], dict):
            for bk in base["buyer"]:
                if bk in partial["buyer"] and partial["buyer"][bk] is not None:
                    base["buyer"][bk] = str(partial["buyer"][bk])
        elif key == "taxes" and isinstance(partial[key], list):
            base["taxes"] = [_normalize_tax(t) for t in partial[key] if isinstance(t, dict)]
        elif key == "line_items" and isinstance(partial[key], list):
            base["line_items"] = [_normalize_line(li) for li in partial[key] if isinstance(li, dict)]
        else:
            base[key] = "" if partial[key] is None else str(partial[key])
    return base


def _normalize_tax(t: dict) -> dict[str, str]:
    out = empty_tax()
    for k in out:
        if k in t and t[k] is not None:
            out[k] = str(t[k]).strip()
    return out


def _normalize_line(li: dict) -> dict[str, Any]:
    out = empty_line_item()
    for k in out:
        if k == "taxes":
            continue
        if k in li and li[k] is not None:
            out[k] = str(li[k]).strip()
    if isinstance(li.get("taxes"), list):
        out["taxes"] = [_normalize_tax(t) for t in li["taxes"] if isinstance(t, dict)]
    item_type = (out.get("item_type") or "SERVICE").upper()
    if item_type not in {"GOODS", "SERVICE", "FREIGHT", "TAX"}:
        item_type = "SERVICE"
    out["item_type"] = item_type
    return out


def deep_copy_payable(p: dict) -> dict:
    return deepcopy(p)
