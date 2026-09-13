#!/usr/bin/env python3
"""Post-process output/*.json to fill master-data codes (never fabricate)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.resolve import MasterIndexes, MasterResolver


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="output")
    ap.add_argument("--master-data", default="master_data")
    args = ap.parse_args()

    resolver = MasterResolver(MasterIndexes.load(args.master_data))
    out = Path(args.output)
    for path in sorted(out.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for p in data.get("payables") or []:
            # reconstruct minimal meta for payment terms from dates only
            before = json.dumps(p, sort_keys=True)
            p = resolver.resolve_payable(p)
            # clear unknowns
            for problem in resolver.assert_code_known(p):
                if "supplier_id" in problem:
                    p["supplier"]["supplier_id"] = ""
                elif "payment_term_id" in problem:
                    p["payment_term_id"] = ""
                elif "po_id" in problem:
                    p["po_id"] = ""
                elif "tax_type_code" in problem:
                    for t in p.get("taxes") or []:
                        if (t.get("tax_type_code") or "") not in resolver.idx.tax_by_code:
                            t["tax_type_code"] = ""
                elif "buyer" in problem:
                    p["buyer"] = {"company_code": "", "business_unit_code": "", "location_code": ""}
            if json.dumps(p, sort_keys=True) != before:
                changed = True
        if changed:
            # re-assign resolved payables
            resolved = []
            for p in data.get("payables") or []:
                resolved.append(resolver.resolve_payable(p))
            data["payables"] = resolved
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("updated", path.name)
        else:
            # still rewrite with resolve once
            data["payables"] = [resolver.resolve_payable(p) for p in (data.get("payables") or [])]
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("resolved", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
