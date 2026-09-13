"""Scalable master-data resolution (keyed indexes, no fabricated codes)."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm_vat(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", (s or "")).upper()


def _norm_iban(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).upper()


@dataclass
class MasterIndexes:
    root: Path
    suppliers_by_id: dict[str, dict] = field(default_factory=dict)
    suppliers_by_vat: dict[str, str] = field(default_factory=dict)
    suppliers_by_iban: dict[str, str] = field(default_factory=dict)
    suppliers_by_name: dict[str, str] = field(default_factory=dict)
    tax_by_code: dict[str, dict] = field(default_factory=dict)
    tax_by_country_rate: dict[tuple[str, float], list[str]] = field(default_factory=dict)
    payment_by_id: dict[str, dict] = field(default_factory=dict)
    payment_by_days: dict[int, str] = field(default_factory=dict)
    payment_aliases: dict[str, str] = field(default_factory=dict)
    po_by_number: dict[str, str] = field(default_factory=dict)
    locations: list[dict] = field(default_factory=list)  # flattened buyer locations

    @classmethod
    def load(cls, master_dir: str | Path) -> "MasterIndexes":
        root = Path(master_dir)
        idx = cls(root=root)

        suppliers = json.loads((root / "suppliers.json").read_text(encoding="utf-8"))
        for s in suppliers.get("suppliers") or []:
            sid = str(s.get("supplier_id") or "")
            if not sid:
                continue
            idx.suppliers_by_id[sid] = s
            vat = _norm_vat(s.get("vat_id") or "")
            if vat:
                idx.suppliers_by_vat[vat] = sid
            iban = _norm_iban(s.get("bank_iban") or "")
            if iban:
                idx.suppliers_by_iban[iban] = sid
            name = _norm(s.get("name") or "")
            if name:
                idx.suppliers_by_name[name] = sid

        taxes = json.loads((root / "tax_master.json").read_text(encoding="utf-8"))
        for t in taxes.get("taxes") or []:
            code = str(t.get("code") or "")
            if not code:
                continue
            idx.tax_by_code[code] = t
            country = str(t.get("country") or "").upper()
            try:
                rate = float(t.get("rate"))
            except (TypeError, ValueError):
                continue
            idx.tax_by_country_rate.setdefault((country, rate), []).append(code)

        terms = json.loads((root / "payment_terms.json").read_text(encoding="utf-8"))
        for pt in terms.get("payment_terms") or []:
            pid = str(pt.get("payment_term_id") or "")
            if not pid:
                continue
            idx.payment_by_id[pid] = pt
            days = int(pt.get("days") or 0)
            idx.payment_by_days[days] = pid
            for alias in pt.get("text_aliases") or []:
                idx.payment_aliases[_norm(alias)] = pid

        pos = json.loads((root / "po_master.json").read_text(encoding="utf-8"))
        for po in pos.get("purchase_orders") or []:
            num = str(po.get("po_number") or po.get("po_id") or "").strip()
            pid = str(po.get("po_id") or "")
            if num and pid:
                idx.po_by_number[_norm(num)] = pid
                idx.po_by_number[num.upper()] = pid

        cob = json.loads((root / "chart_of_books.json").read_text(encoding="utf-8"))
        for co in cob.get("companies") or []:
            company_code = str(co.get("company_code") or "")
            company_name = str(co.get("company_name") or "")
            for bu in co.get("business_units") or []:
                bu_code = str(bu.get("business_unit_code") or "")
                bu_name = str(bu.get("business_unit_name") or "")
                for loc in bu.get("locations") or []:
                    idx.locations.append(
                        {
                            "company_code": company_code,
                            "company_name": company_name,
                            "business_unit_code": bu_code,
                            "business_unit_name": bu_name,
                            "location_code": str(loc.get("location_code") or ""),
                            "location_name": str(loc.get("location_name") or ""),
                            "invoice_to_address": str(loc.get("invoice_to_address") or ""),
                            "_addr_norm": _norm(str(loc.get("invoice_to_address") or "")),
                            "_bu_norm": _norm(bu_name),
                            "_loc_norm": _norm(str(loc.get("location_name") or "")),
                        }
                    )
        return idx


class MasterResolver:
    def __init__(self, indexes: MasterIndexes):
        self.idx = indexes

    def resolve_payable(self, payable: dict[str, Any]) -> dict[str, Any]:
        meta = payable.get("_meta") or {}
        supplier = payable.setdefault("supplier", {})
        supplier_id = self.match_supplier(
            name=supplier.get("name") or "",
            vat_id=supplier.get("vat_id") or "",
            address=supplier.get("address") or "",
        )
        supplier["supplier_id"] = supplier_id

        buyer_text = meta.get("buyer_text") if isinstance(meta.get("buyer_text"), dict) else {}
        buyer = self.match_buyer(
            name=(buyer_text or {}).get("name") or "",
            address=(buyer_text or {}).get("address") or "",
        )
        payable["buyer"] = buyer

        payable["payment_term_id"] = self.match_payment_term(
            text=str(meta.get("payment_terms_text") or ""),
            invoice_date=payable.get("invoice_date") or "",
            due_date=payable.get("due_date") or "",
        )

        po_number = str(payable.get("po_number") or "").strip()
        payable["po_number"] = po_number
        payable["po_id"] = self.match_po(po_number)

        # Resolve tax codes on header and lines
        country_hint = self._supplier_country(supplier_id)
        for t in payable.get("taxes") or []:
            if isinstance(t, dict):
                t["tax_type_code"] = self.match_tax(
                    tax_name=t.get("tax_name") or "",
                    tax_rate=t.get("tax_rate") or "",
                    tax_type=t.get("tax_type") or "",
                    country=country_hint,
                )
        for li in payable.get("line_items") or []:
            if not isinstance(li, dict):
                continue
            for t in li.get("taxes") or []:
                if isinstance(t, dict):
                    t["tax_type_code"] = self.match_tax(
                        tax_name=t.get("tax_name") or "",
                        tax_rate=t.get("tax_rate") or li.get("tax_rate") or "",
                        tax_type=t.get("tax_type") or "",
                        country=country_hint,
                    )
        return payable

    def match_supplier(self, *, name: str, vat_id: str, address: str = "") -> str:
        vat = _norm_vat(vat_id)
        if vat and vat in self.idx.suppliers_by_vat:
            return self.idx.suppliers_by_vat[vat]
        # IBAN sometimes appears in address blocks
        iban_m = re.search(r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b", (address or "").upper().replace(" ", ""))
        if iban_m:
            iban = _norm_iban(iban_m.group(1))
            if iban in self.idx.suppliers_by_iban:
                return self.idx.suppliers_by_iban[iban]
        n = _norm(name)
        if n and n in self.idx.suppliers_by_name:
            return self.idx.suppliers_by_name[n]
        # conservative token containment — only if unique
        if n:
            hits = []
            for master_name, sid in self.idx.suppliers_by_name.items():
                if n in master_name or master_name in n:
                    hits.append(sid)
            hits = list(dict.fromkeys(hits))
            if len(hits) == 1:
                return hits[0]
        return ""

    def match_buyer(self, *, name: str, address: str) -> dict[str, str]:
        empty = {"company_code": "", "business_unit_code": "", "location_code": ""}
        addr = _norm(address)
        nm = _norm(name)
        if not addr and not nm:
            # Default tenant often Bolt Group when address missing — leave blank (honest).
            return empty

        best = None
        best_score = 0
        for loc in self.idx.locations:
            score = 0
            if addr and loc["_addr_norm"]:
                if addr == loc["_addr_norm"]:
                    score += 10
                else:
                    # token overlap
                    a_toks = set(addr.split())
                    b_toks = set(loc["_addr_norm"].split())
                    if a_toks and b_toks:
                        overlap = len(a_toks & b_toks) / max(1, len(a_toks | b_toks))
                        if overlap >= 0.45:
                            score += int(overlap * 8)
            if nm:
                if nm in loc["_bu_norm"] or loc["_bu_norm"] in nm:
                    score += 4
                if "bolt" in nm and "bolt" in _norm(loc["company_name"]):
                    score += 2
            if score > best_score:
                best_score = score
                best = loc
        if best and best_score >= 4:
            return {
                "company_code": best["company_code"],
                "business_unit_code": best["business_unit_code"],
                "location_code": best["location_code"],
            }
        return empty

    def match_payment_term(self, *, text: str, invoice_date: str, due_date: str) -> str:
        t = _norm(text)
        if t and t in self.idx.payment_aliases:
            return self.idx.payment_aliases[t]
        # substring alias
        for alias, pid in self.idx.payment_aliases.items():
            if alias and alias in t:
                return pid
        days = _date_delta_days(invoice_date, due_date)
        if days is not None and days in self.idx.payment_by_days:
            return self.idx.payment_by_days[days]
        return ""

    def match_po(self, po_number: str) -> str:
        if not po_number:
            return ""
        if po_number.upper() in self.idx.po_by_number:
            return self.idx.po_by_number[po_number.upper()]
        n = _norm(po_number)
        return self.idx.po_by_number.get(n, "")

    def match_tax(self, *, tax_name: str, tax_rate: str, tax_type: str, country: str) -> str:
        try:
            rate = float(str(tax_rate).replace("%", "").strip() or "nan")
        except ValueError:
            rate = float("nan")
        country = (country or "").upper()
        if country and rate == rate:  # not NaN
            codes = self.idx.tax_by_country_rate.get((country, rate), [])
            if len(codes) == 1:
                return codes[0]
            if len(codes) > 1:
                # disambiguate by name keywords
                name_n = _norm(tax_name)
                for code in codes:
                    t = self.idx.tax_by_code[code]
                    if _norm(t.get("name") or "") and (
                        name_n in _norm(t.get("name") or "") or _norm(t.get("name") or "") in name_n
                    ):
                        return code
                # reverse charge keyword
                if "reverse" in name_n:
                    for code in codes:
                        if "rc" in code.lower() or "reverse" in _norm(self.idx.tax_by_code[code].get("name") or ""):
                            return code
                return ""  # ambiguous — honest blank
        # global unique rate+type fallback (only if unique across master)
        if rate == rate:
            hits = [
                code
                for code, t in self.idx.tax_by_code.items()
                if float(t.get("rate")) == rate
                and (not tax_type or str(t.get("tax_type") or "").upper() == tax_type.upper())
            ]
            if len(hits) == 1:
                return hits[0]
        return ""

    def _supplier_country(self, supplier_id: str) -> str:
        s = self.idx.suppliers_by_id.get(supplier_id) or {}
        return str(s.get("country") or "").upper()

    def assert_code_known(self, payable: dict) -> list[str]:
        """Return list of fabricated-code problems (should be empty after resolve)."""
        problems = []
        sid = payable.get("supplier", {}).get("supplier_id") or ""
        if sid and sid not in self.idx.suppliers_by_id:
            problems.append(f"unknown supplier_id {sid}")
        pid = payable.get("payment_term_id") or ""
        if pid and pid not in self.idx.payment_by_id:
            problems.append(f"unknown payment_term_id {pid}")
        po_id = payable.get("po_id") or ""
        if po_id and po_id not in {v for v in self.idx.po_by_number.values()}:
            problems.append(f"unknown po_id {po_id}")
        buyer = payable.get("buyer") or {}
        if any(buyer.get(k) for k in ("company_code", "business_unit_code", "location_code")):
            ok = any(
                loc["company_code"] == buyer.get("company_code")
                and loc["business_unit_code"] == buyer.get("business_unit_code")
                and loc["location_code"] == buyer.get("location_code")
                for loc in self.idx.locations
            )
            if not ok and buyer.get("company_code"):
                problems.append(f"unknown buyer combo {buyer}")
        for t in payable.get("taxes") or []:
            code = (t or {}).get("tax_type_code") or ""
            if code and code not in self.idx.tax_by_code:
                problems.append(f"unknown tax_type_code {code}")
        return problems


def _date_delta_days(invoice_date: str, due_date: str) -> int | None:
    try:
        a = datetime.strptime(invoice_date[:10], "%Y-%m-%d")
        b = datetime.strptime(due_date[:10], "%Y-%m-%d")
        return (b - a).days
    except (ValueError, TypeError, IndexError):
        return None
