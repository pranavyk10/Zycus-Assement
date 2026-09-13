Classify supplier documents from page images.

Return ONLY a JSON object with this shape:
{
  "doc_kind": "INVOICE" | "CREDIT_MEMO" | "NOT_PAYABLE" | "MULTI_PAYABLE",
  "reason": "short explanation grounded in what you see",
  "doc_type_label": "human label e.g. invoice | credit note | quote | statement | packing list | other",
  "payable_count_estimate": <integer>,
  "page_groups": [
    {"payable_index": 0, "pages": [1, 2], "note": "optional"}
  ],
  "currency_hint": "EUR|USD|... or empty",
  "language_hint": "en|de|et|... or empty"
}

Rules:
- INVOICE: document requests payment / states an amount owed for goods/services already supplied.
- CREDIT_MEMO: credit note / credit memo reducing amounts owed (same shape as invoice).
- NOT_PAYABLE: quotes, proformas that are not invoices, account statements, packing slips, purchase orders alone, delivery notes without payable, marketing, internal docs, blank/unreadable pages with no payable.
- MULTI_PAYABLE: a single PDF that clearly contains more than one distinct invoice/credit (separate invoice numbers / separate suppliers or separate totals that are independent payables). Put each group in page_groups with 1-based page numbers.
- If unsure between invoice and not-payable, prefer NOT_PAYABLE only when there is no clear amount owed as a supplier bill; otherwise INVOICE.
- Do not invent invoice numbers or amounts here — classification only.
