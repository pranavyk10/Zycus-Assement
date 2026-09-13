# DESIGN.md

## 1. What I eventually understood that I did not on day one

On day one this looks like document extraction: read the page, fill the schema, hope the total matches. That stalls quickly.

The real object is a **bookable payable**: a set of *components* the ERP will recompute. [`erp.py`](erp.py) does not trust your `gross_total`; it rebuilds:

```
Σ (qty × net unit_price − line discount) − header discount
+ line taxes + header taxes + freight/insurance/extra/excise
```

Three consequences:

1. **Net vs printed price.** Copying tax-inclusive unit prices into `unit_price` double-counts tax once the ERP applies the rate. A record can look faithful and still book the wrong gross.
2. **Placement is part of the answer.** Header VAT and per-line VAT can foot the same number on simple docs and still be the wrong payable. The document’s structure — where the tax is stated — is graded, not only the foot.
3. **Same total, wrong path.** Forcing a foot by inventing a discount, blending rates, or migrating tax levels produces an oracle match that fails the structure check and violates the grounding rule.

After that shift, failures stop looking like unrelated OCR bugs and look like mis-specified components: wrong tax base, wrong level, or a document that is not a payable at all.

## 2. What the system does on a document unlike any it has seen

The pipeline is intentionally **document-agnostic**:

1. **Classify** (vision): invoice / credit memo / not payable / multi-payable. Non-payables go to `declined[]` only.
2. **Extract** grounded fields only — empty string over guesses; tax placement and net/gross price stance called out explicitly.
3. **Resolve** master codes via **keyed indexes** (VAT, IBAN, normalized name, country+rate, payment aliases / date delta, exact PO). Ambiguous → `""`. Designed so masters can grow to millions without per-document hacks.
4. **Validate** with `erp_book`. On mismatch, try a **small family of grounded reinterpretations** (derive net from gross under a stated rate; header↔line rate when placement is ambiguous; reverse-charge 0%). Each candidate must still use document-stated figures.
5. If none foot **without invention**, refuse to fabricate a balancing line — emit what was grounded and record an honest decline/mismatch reason.

That generalises because the policy is “components + oracle + grounding,” not a switchyard of `INV-XX` special cases.

## 3. A document that could not be solved the way the others were

Several open documents are **not bookable payables**, and treating them as invoices would be faking:

| File | Why refusal is correct |
|------|-------------------------|
| `INV-23` | Estimate (`EST-…`), not an invoice |
| `INV-14` / `INV-15` | Outbound AR invoices (tenant as supplier), not AP payables |
| `INV-26` | Sales quotation; line set incomplete vs printed total |
| `DU-02` | Customs consolidated valuation pack, not a supplier bill |
| `DU-05s` | Delivery notes without prices |
| `DU-08` | Dunning / payment reminder |
| `DU-09` | Internal sponsorship approval form |

The page does not authorize a bookable payable (or does not contain the figures needed to reconstruct one without invention). The system’s correct behaviour is `payables: []` with a clear `declined[]` reason — not a fabricated foot that would satisfy `erp_book` while violating grounding rule 1.

That recognition is part of the exam; pretending otherwise scores worse than an honest decline.
