"""Document classification via vision LLM."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .ingest import PageImage
from .llm_client import chat_vision_json

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def classify_document(pages: list[PageImage], file_name: str) -> dict[str, Any]:
    """Return classification dict with doc_kind and optional page_groups."""
    if not pages:
        return {
            "doc_kind": "NOT_PAYABLE",
            "reason": "empty PDF",
            "doc_type_label": "empty",
            "payable_count_estimate": 0,
            "page_groups": [],
        }

    # Cap images sent for classification to control cost on long packs.
    sample = pages if len(pages) <= 6 else pages[:3] + pages[-2:]
    system = _load_prompt("classify.md")
    user = (
        f"File name: {file_name}\n"
        f"Total pages: {len(pages)}\n"
        f"You are seeing {len(sample)} page image(s) "
        f"(page indexes 0-based in order: {[p.page_index for p in sample]}).\n"
        "Classify the document."
    )
    result = chat_vision_json(system, user, [p.data_url for p in sample])
    kind = str(result.get("doc_kind") or "INVOICE").upper().strip()
    if kind not in {"INVOICE", "CREDIT_MEMO", "NOT_PAYABLE", "MULTI_PAYABLE"}:
        kind = "INVOICE"
    result["doc_kind"] = kind
    if "page_groups" not in result or not isinstance(result["page_groups"], list):
        result["page_groups"] = []
    return result
