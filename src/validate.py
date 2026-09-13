"""ERP oracle validation and grounded repair families."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from erp import erp_book, num, round2

from .normalize import derive_net_from_gross_prices, normalize_payable_numbers, strip_meta


def gross_matches(payable: dict, *, tol: float = 0.01) -> tuple[bool, float, float]:
    """Compare erp_book gross to printed gross_total."""
    printed = num(payable.get("gross_total"))
    result = erp_book(strip_meta(payable))
    booked = float(result["will_book_gross"])
    return abs(booked - printed) <= tol, booked, printed


def validate_and_repair(
    payable: dict,
    *,
    prices_are_tax_inclusive: bool = False,
    tax_placement: str = "unknown",
) -> dict[str, Any]:
    """Try grounded reinterpretations until ERP foots, or mark unsolvable.

    Never invents numbers. Only reinterprets structure/netness using document-stated rates.
    """
    p = normalize_payable_numbers(payable)
    meta = p.get("_meta") or {}
    unsolvable = bool(meta.get("unsolvable"))
    candidates: list[tuple[str, dict]] = [("as_extracted", deepcopy(p))]

    rate = _primary_rate(p)
    if prices_are_tax_inclusive or meta.get("prices_are_tax_inclusive"):
        if rate and rate > 0:
            derived = derive_net_from_gross_prices(p, tax_rate=rate)
            if derived is not None:
                candidates.append(("net_from_gross_unit_prices", derived))

    # If header has a rate but tax_amount empty / zero and lines look net — keep as-is (already candidate)
    # Try moving a single header tax onto each line when placement unknown and one rate exists
    if tax_placement in {"unknown", "mixed", "line"} and rate is not None:
        line_taxed = _push_header_tax_to_lines(p, rate)
        if line_taxed is not None:
            candidates.append(("header_rate_to_lines", line_taxed))

    if tax_placement in {"unknown", "mixed", "header"} and rate is not None:
        headered = _collapse_line_rates_to_header(p, rate)
        if headered is not None:
            candidates.append(("line_rates_to_header", headered))

    # Explicit printed tax_amount with rate 0 (reverse charge / withholding)
    rc = _ensure_reverse_charge(p)
    if rc is not None:
        candidates.append(("reverse_charge", rc))

    # Withholding only when an explicit negative tax_amount was extracted from the page
    # (never invent a gap-filler amount — that violates grounding rule 1).

    best: dict | None = None
    best_diff = float("inf")
    best_label = ""
    for label, cand in candidates:
        # Clear fabricated codes check is elsewhere; here only arithmetic
        ok, booked, printed = gross_matches(cand)
        diff = abs(booked - printed)
        if ok:
            out = strip_meta(cand)
            return {
                "payable": out,
                "ok": True,
                "repair": label,
                "will_book_gross": booked,
                "printed_gross": printed,
            }
        if diff < best_diff:
            best_diff = diff
            best = cand
            best_label = label

    # No candidate foots — refuse to invent. Emit best extraction stripped, flagged.
    out = strip_meta(best or p)
    return {
        "payable": out,
        "ok": False,
        "repair": best_label or "none",
        "will_book_gross": erp_book(out)["will_book_gross"],
        "printed_gross": num(out.get("gross_total")),
        "unsolvable": True if unsolvable or best_diff > 0.01 else False,
        "diff": best_diff,
    }


def _primary_rate(payable: dict) -> float | None:
    rates: list[float] = []
    for t in payable.get("taxes") or []:
        if isinstance(t, dict):
            r = num(t.get("tax_rate"))
            if str(t.get("tax_rate") or "").strip() != "":
                rates.append(r)
    for li in payable.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        if str(li.get("tax_rate") or "").strip():
            rates.append(num(li.get("tax_rate")))
        for t in li.get("taxes") or []:
            if isinstance(t, dict) and str(t.get("tax_rate") or "").strip():
                rates.append(num(t.get("tax_rate")))
    rates = [r for r in rates if r == r]
    if not rates:
        return None
    # unique positive or zero
    uniq = sorted(set(rates))
    if len(uniq) == 1:
        return uniq[0]
    # prefer most common
    return max(set(rates), key=rates.count)


def _push_header_tax_to_lines(payable: dict, rate: float) -> dict | None:
    p = deepcopy(payable)
    header_taxes = p.get("taxes") or []
    if not header_taxes and rate <= 0:
        return None
    # Only when lines currently have no tax
    lines = p.get("line_items") or []
    if not lines:
        return None
    if any(
        (li.get("tax_rate") or li.get("tax_amount") or (li.get("taxes") or []))
        for li in lines
        if isinstance(li, dict)
    ):
        return None
    name = ""
    tax_type = "VAT"
    if header_taxes and isinstance(header_taxes[0], dict):
        name = header_taxes[0].get("tax_name") or ""
        tax_type = header_taxes[0].get("tax_type") or "VAT"
    for li in lines:
        if not isinstance(li, dict):
            continue
        li["tax_rate"] = _rate_str(rate)
        li["taxes"] = [
            {
                "tax_type": tax_type,
                "tax_name": name,
                "tax_rate": _rate_str(rate),
                "tax_amount": "",
                "tax_type_code": "",
            }
        ]
    p["taxes"] = []
    return p


def _collapse_line_rates_to_header(payable: dict, rate: float) -> dict | None:
    p = deepcopy(payable)
    lines = p.get("line_items") or []
    if not lines:
        return None
    # Only if every taxed line shares the same rate and header empty
    line_rates = []
    for li in lines:
        if not isinstance(li, dict):
            continue
        if li.get("taxes"):
            for t in li["taxes"]:
                if isinstance(t, dict) and str(t.get("tax_rate") or "").strip() != "":
                    line_rates.append(num(t.get("tax_rate")))
        elif str(li.get("tax_rate") or "").strip():
            line_rates.append(num(li.get("tax_rate")))
    if not line_rates or len(set(line_rates)) != 1:
        return None
    if p.get("taxes"):
        return None
    for li in lines:
        if not isinstance(li, dict):
            continue
        li["tax_rate"] = ""
        li["tax_amount"] = ""
        li["taxes"] = []
    p["taxes"] = [
        {
            "tax_type": "VAT",
            "tax_name": "",
            "tax_rate": _rate_str(rate),
            "tax_amount": "",
            "tax_type_code": "",
        }
    ]
    return p


def _ensure_reverse_charge(payable: dict) -> dict | None:
    p = deepcopy(payable)
    changed = False
    for t in p.get("taxes") or []:
        if not isinstance(t, dict):
            continue
        name = (t.get("tax_name") or "").lower()
        if "reverse" in name or "rc" == name.strip():
            if not str(t.get("tax_rate") or "").strip():
                t["tax_rate"] = "0"
                changed = True
            if not str(t.get("tax_amount") or "").strip():
                t["tax_amount"] = "0.00"
                changed = True
    return p if changed else None


def _rate_str(rate: float) -> str:
    if abs(rate - round(rate)) < 1e-9:
        return str(int(round(rate)))
    return f"{rate:.4f}".rstrip("0").rstrip(".")
