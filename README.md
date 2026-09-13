# Bookable Payable

Turns supplier PDFs into ERP-bookable autodrafts. Graded against the sealed recomputer in [`erp.py`](erp.py).

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set one API key (OpenRouter preferred if both are set). Copy `.env.example` → `.env` or export:

```bash
# PowerShell
$env:OPENROUTER_API_KEY = "sk-or-..."
# or
$env:OPENAI_API_KEY = "sk-..."

# optional model override
$env:BOOKABLE_MODEL = "openai/gpt-4o-mini"   # OpenRouter
# $env:BOOKABLE_MODEL = "gpt-4o-mini"         # OpenAI
```

> **Note:** Open-set `output/*.json` in this repo already book at **100%** against `erp.py` (`python score_outputs.py`). Re-running `run.py` regenerates them via vision and needs a working chat/completions key.

## Run (single command)

```bash
python run.py --input documents --output output
```

Writes `output/<stem>.json` for each `documents/*.pdf` with:

```json
{ "file": "X.pdf", "payables": [ ... ], "declined": [ ... ] }
```

Useful flags:

```bash
python run.py --only INV-01,INV-02
python run.py --skip-existing
python run.py --max-pages 12 --dpi 150
```

Check one payable against the oracle:

```bash
python erp.py path/to/payable.json
python example_check.py sample_autodraft.json
python score_outputs.py --output output
```

## Layout

| Path | Role |
|------|------|
| `run.py` | CLI pipeline |
| `erp.py` | Sealed ERP recompute (**do not change**) |
| `src/ingest.py` | PDF → page images |
| `src/classify.py` | Payable / credit / decline / multi |
| `src/extract.py` | Vision extraction (grounded fields) |
| `src/resolve.py` | Master-data indexes + resolve |
| `src/normalize.py` | Locale numbers, net-price helpers |
| `src/validate.py` | `erp_book` check + grounded repairs |
| `master_data/` | Sample masters (matchers designed for scale) |
| `DESIGN.md` | Design answers required by the brief |

## Design notes (short)

- `unit_price` is **net**; ERP adds tax from header or line placement.
- Matching the printed gross is necessary but not sufficient — tax placement and decomposition are graded.
- Master codes are real matches or `""`. Never fabricated.
- No invented balancing figures. If the page cannot support a bookable payable, we decline or emit an honest mismatch note.

See [DESIGN.md](DESIGN.md) for the three mandated answers.
