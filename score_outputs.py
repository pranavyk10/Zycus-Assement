#!/usr/bin/env python3
"""Score open-set outputs against erp_book vs printed gross_total."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from erp import erp_book, num


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="output")
    args = ap.parse_args()
    out = Path(args.output)
    files = sorted(out.glob("*.json"))
    if not files:
        print("No output JSON found")
        return 1

    booked_ok = 0
    payable_n = 0
    declined_only = 0
    mismatches = []

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        pays = data.get("payables") or []
        if not pays:
            declined_only += 1
            continue
        for i, p in enumerate(pays):
            payable_n += 1
            printed = num(p.get("gross_total"))
            booked = float(erp_book(p)["will_book_gross"])
            if abs(booked - printed) <= 0.01:
                booked_ok += 1
            else:
                mismatches.append((f.name, i, booked, printed))

    print(f"files={len(files)} declined_or_empty={declined_only}")
    print(f"payables={payable_n} oracle_match={booked_ok}")
    if payable_n:
        print(f"match_rate={booked_ok / payable_n:.1%}")
    for name, i, booked, printed in mismatches[:30]:
        print(f"  MISMATCH {name}[{i}]: booked={booked} printed={printed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
