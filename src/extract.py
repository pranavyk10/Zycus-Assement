"""Vision LLM extraction of grounded autodraft components."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .ingest import PageImage
from .llm_client import chat_vision_json
from .schema import merge_payable

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def extract_from_pages(
    pages: list[PageImage],
    file_name: str,
    *,
    doc_kind_hint: str = "",
    max_pages_per_call: int = 8,
) -> dict[str, Any]:
    """Extract payables/declined from page images. Chunks long PDFs."""
    if not pages:
        return {
            "payables": [],
            "declined": [{"doc_type": "empty", "reason": "no pages"}],
            "prices_are_tax_inclusive": False,
            "tax_placement": "none",
        }

    system = _load_prompt("extract.md")
    chunks = _chunk(pages, max_pages_per_call)
    merged_payables: list[dict] = []
    merged_declined: list[dict] = []
    prices_inclusive = False
    tax_placement = "unknown"

    for chunk in chunks:
        user = (
            f"File: {file_name}\n"
            f"Classification hint: {doc_kind_hint or 'unknown'}\n"
            f"Pages in this call (0-based): {[p.page_index for p in chunk]} "
            f"of {len(pages)} total.\n"
            "Extract bookable payable components. If this chunk is only a continuation "
            "of a payable already started, still extract the full payable if possible; "
            "otherwise extract what is complete on these pages."
        )
        result = chat_vision_json(system, user, [p.data_url for p in chunk])
        prices_inclusive = prices_inclusive or bool(result.get("prices_are_tax_inclusive"))
        tp = str(result.get("tax_placement") or "").lower()
        if tp in {"header", "line", "mixed", "none"}:
            tax_placement = tp
        for p in result.get("payables") or []:
            if isinstance(p, dict):
                merged_payables.append(p)
        for d in result.get("declined") or []:
            if isinstance(d, dict):
                merged_declined.append(d)

    # Deduplicate near-identical invoice numbers from overlapping chunks.
    merged_payables = _dedupe_payables(merged_payables)
    return {
        "payables": merged_payables,
        "declined": merged_declined,
        "prices_are_tax_inclusive": prices_inclusive,
        "tax_placement": tax_placement,
    }


def to_schema_payables(raw_payables: list[dict], *, default_type: str = "INVOICE") -> list[dict]:
    out = []
    for raw in raw_payables:
        if not isinstance(raw, dict):
            continue
        # Stash meta then merge into schema
        meta = {
            "prices_are_tax_inclusive": raw.pop("prices_are_tax_inclusive", None),
            "buyer_text": raw.pop("buyer_text", None),
            "payment_terms_text": raw.pop("payment_terms_text", None),
            "notes": raw.pop("notes", None),
            "unsolvable": raw.pop("unsolvable", False),
            "unsolvable_reason": raw.pop("unsolvable_reason", ""),
        }
        if not raw.get("invoice_type"):
            raw["invoice_type"] = default_type
        # buyer_text is not in schema; buyer codes filled by resolver
        payable = merge_payable(raw)
        payable["_meta"] = meta
        out.append(payable)
    return out


def _chunk(pages: list[PageImage], size: int) -> list[list[PageImage]]:
    if size <= 0:
        return [pages]
    return [pages[i : i + size] for i in range(0, len(pages), size)]


def _dedupe_payables(payables: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in payables:
        key = f"{p.get('invoice_number','')}|{p.get('gross_total','')}|{p.get('currency','')}"
        if key in seen and key != "||":
            continue
        seen.add(key)
        out.append(p)
    return out
