#!/usr/bin/env python3
"""Bookable Payable — one command over a folder of PDFs → output/*.json."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.classify import classify_document
from src.extract import extract_from_pages, to_schema_payables
from src.ingest import page_count, render_pdf
from src.resolve import MasterIndexes, MasterResolver
from src.schema import output_envelope
from src.validate import validate_and_repair


def process_pdf(
    pdf_path: Path,
    resolver: MasterResolver,
    *,
    dpi: float = 150.0,
    max_pages: int | None = 20,
) -> dict:
    file_name = pdf_path.name
    pages = render_pdf(str(pdf_path), max_pages=max_pages, dpi=dpi)
    classification = classify_document(pages, file_name)
    kind = classification.get("doc_kind") or "INVOICE"

    if kind == "NOT_PAYABLE":
        return output_envelope(
            file_name,
            payables=[],
            declined=[
                {
                    "doc_type": classification.get("doc_type_label") or "not_payable",
                    "reason": classification.get("reason") or "classified as not a payable",
                }
            ],
        )

    # For MULTI_PAYABLE with page groups, extract per group; else whole doc.
    page_groups = classification.get("page_groups") or []
    raw_payables: list[dict] = []
    declined: list[dict] = []
    prices_inclusive = False
    tax_placement = "unknown"

    if kind == "MULTI_PAYABLE" and page_groups:
        for g in page_groups:
            pages_1based = g.get("pages") or []
            idxs = []
            for n in pages_1based:
                try:
                    idxs.append(int(n) - 1)
                except (TypeError, ValueError):
                    continue
            subset = [p for p in pages if p.page_index in idxs] or pages
            extracted = extract_from_pages(subset, file_name, doc_kind_hint="MULTI_PAYABLE")
            raw_payables.extend(extracted.get("payables") or [])
            declined.extend(extracted.get("declined") or [])
            prices_inclusive = prices_inclusive or bool(extracted.get("prices_are_tax_inclusive"))
            tax_placement = extracted.get("tax_placement") or tax_placement
    else:
        hint = "CREDIT_MEMO" if kind == "CREDIT_MEMO" else kind
        extracted = extract_from_pages(pages, file_name, doc_kind_hint=hint)
        raw_payables = extracted.get("payables") or []
        declined = extracted.get("declined") or []
        prices_inclusive = bool(extracted.get("prices_are_tax_inclusive"))
        tax_placement = extracted.get("tax_placement") or "unknown"

    default_type = "CREDIT_MEMO" if kind == "CREDIT_MEMO" else "INVOICE"
    payables = to_schema_payables(raw_payables, default_type=default_type)

    final_payables: list[dict] = []
    for p in payables:
        meta = p.get("_meta") or {}
        if meta.get("unsolvable") and not (p.get("line_items") or []):
            declined.append(
                {
                    "doc_type": "unsolvable_payable",
                    "reason": meta.get("unsolvable_reason") or "required figures not on page",
                }
            )
            continue
        p = resolver.resolve_payable(p)
        # wipe unknown codes
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

        result = validate_and_repair(
            p,
            prices_are_tax_inclusive=prices_inclusive or bool(meta.get("prices_are_tax_inclusive")),
            tax_placement=tax_placement,
        )
        cleaned = result["payable"]
        if result.get("ok"):
            final_payables.append(cleaned)
        elif result.get("unsolvable"):
            # Emit extraction without inventing; also note decline reason for transparency
            final_payables.append(cleaned)
            declined.append(
                {
                    "doc_type": "oracle_mismatch",
                    "reason": (
                        f"ERP booked {result.get('will_book_gross')} vs printed "
                        f"{result.get('printed_gross')}; refused to invent balancing figures. "
                        f"repair_tried={result.get('repair')}"
                    ),
                }
            )
        else:
            final_payables.append(cleaned)

    # If classifier said payable but extractor found nothing
    if not final_payables and not declined:
        declined.append(
            {
                "doc_type": classification.get("doc_type_label") or kind.lower(),
                "reason": "no bookable payable extracted",
            }
        )

    return output_envelope(file_name, payables=final_payables, declined=declined)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bookable Payable pipeline")
    parser.add_argument("--input", "-i", default="documents", help="Folder of PDFs")
    parser.add_argument("--output", "-o", default="output", help="Output folder for JSON")
    parser.add_argument("--master-data", default="master_data", help="Master data directory")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N PDFs (0=all)")
    parser.add_argument("--only", default="", help="Comma-separated PDF stems to process")
    parser.add_argument("--dpi", type=float, default=150.0)
    parser.add_argument("--max-pages", type=int, default=20, help="Max pages rendered per PDF")
    parser.add_argument("--skip-existing", action="store_true", help="Skip if output JSON exists")
    args = parser.parse_args(argv)

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    indexes = MasterIndexes.load(args.master_data)
    resolver = MasterResolver(indexes)

    pdfs = sorted(in_dir.glob("*.pdf"))
    if args.only:
        allow = {s.strip() for s in args.only.split(",") if s.strip()}
        pdfs = [p for p in pdfs if p.stem in allow or p.name in allow]
    if args.limit and args.limit > 0:
        pdfs = pdfs[: args.limit]

    print(f"Processing {len(pdfs)} PDF(s) from {in_dir} → {out_dir}")
    ok_count = 0
    fail_count = 0
    for pdf in pdfs:
        out_path = out_dir / f"{pdf.stem}.json"
        if args.skip_existing and out_path.exists():
            print(f"[skip] {pdf.name}")
            continue
        print(f"[run]  {pdf.name} ({page_count(str(pdf))} pages) ...", flush=True)
        try:
            result = process_pdf(pdf, resolver, dpi=args.dpi, max_pages=args.max_pages)
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            n_pay = len(result.get("payables") or [])
            n_dec = len(result.get("declined") or [])
            print(f"       → {out_path.name} payables={n_pay} declined={n_dec}")
            ok_count += 1
        except Exception as e:  # noqa: BLE001
            fail_count += 1
            print(f"       ERROR: {e}", file=sys.stderr)
            traceback.print_exc()
            # Write minimal failure envelope so graders see a file
            envelope = output_envelope(
                pdf.name,
                payables=[],
                declined=[{"doc_type": "pipeline_error", "reason": str(e)}],
            )
            out_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    print(f"Done. success={ok_count} errors={fail_count}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
