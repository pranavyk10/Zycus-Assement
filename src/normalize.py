"""Normalize numbers, net prices, and tax placement without inventing figures."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from erp import num, round2


_CURRENCY = "€$£¥₹"


def to_dot_decimal(value: Any) -> str:
    """Normalize locale number strings to ERP dot-decimal; empty if unparseable."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}" if not float(value).is_integer() else str(value)
    s = str(value).strip()
    if not s:
        return ""
    s = s.replace("%", "").strip()
    # strip currency symbols
    s = re.sub(r"^[" + re.escape(_CURRENCY) + r"\s]+", "", s)
    s = re.sub(r"[" + re.escape(_CURRENCY) + r"\s]+$", "", s)
    s = s.strip()
    # European: 1.234,56 → 1234.56
    if re.match(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$", s) or re.match(r"^-?\d+,\d+$", s):
        s = s.replace(".", "").replace(",", ".")
    # US with commas: 1,234.56
    elif re.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", s):
        s = s.replace(",", "")
    try:
        float(s)
        return s
    except ValueError:
        return ""


def normalize_payable_numbers(payable: dict) -> dict:
    p = deepcopy(payable)
    for key in (
        "gross_total",
        "subtotal",
        "total_tax_amount",
        "discount_amount",
        "freight_charges",
        "insurance_charges",
        "extra_charges",
        "excise_duties",
    ):
        if key in p:
            p[key] = to_dot_decimal(p.get(key))
    for t in p.get("taxes") or []:
        if isinstance(t, dict):
            t["tax_rate"] = to_dot_decimal(t.get("tax_rate")).rstrip("0").rstrip(".") if to_dot_decimal(t.get("tax_rate")) else to_dot_decimal(t.get("tax_rate"))
            # keep rate as clean string
            rate = to_dot_decimal(t.get("tax_rate"))
            t["tax_rate"] = _clean_rate(rate)
            t["tax_amount"] = to_dot_decimal(t.get("tax_amount"))
    for li in p.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        for k in ("quantity", "unit_price", "total", "discount", "discount_percentage", "tax_rate", "tax_amount"):
            if k in li:
                if k in ("tax_rate", "discount_percentage"):
                    li[k] = _clean_rate(to_dot_decimal(li.get(k)))
                else:
                    li[k] = to_dot_decimal(li.get(k))
        for t in li.get("taxes") or []:
            if isinstance(t, dict):
                t["tax_rate"] = _clean_rate(to_dot_decimal(t.get("tax_rate")))
                t["tax_amount"] = to_dot_decimal(t.get("tax_amount"))
    return p


def _clean_rate(rate: str) -> str:
    if not rate:
        return ""
    try:
        f = float(rate)
        if abs(f - round(f)) < 1e-9:
            return str(int(round(f)))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except ValueError:
        return rate


def derive_net_from_gross_prices(payable: dict, *, tax_rate: float) -> dict | None:
    """If prices appear tax-inclusive and a single rate is known, derive NET unit prices.

    Only uses the stated rate — does not invent amounts. Returns None if rate invalid.
    """
    if tax_rate <= 0:
        return None
    p = deepcopy(payable)
    factor = 1.0 + tax_rate / 100.0
    for li in p.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        up = num(li.get("unit_price"))
        if up == 0:
            continue
        li["unit_price"] = f"{round2(up / factor):.2f}"
        # line total if present and looks gross
        tot = num(li.get("total"))
        if tot:
            li["total"] = f"{round2(tot / factor):.2f}"
    return p


def strip_meta(payable: dict) -> dict:
    p = deepcopy(payable)
    p.pop("_meta", None)
    return p


def ensure_tax_fields(payable: dict, tax_placement: str) -> dict:
    """Light cleanup: if line has tax_rate but empty taxes[], leave as-is (ERP accepts both)."""
    p = deepcopy(payable)
    placement = (tax_placement or "").lower()
    if placement == "header":
        # clear accidental line tax rates if header is authoritative and lines have none amounts
        pass
    return p
