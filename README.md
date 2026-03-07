# Passport + G-28 Document Automation

Extracts structured data from a passport and G-28 form using an LLM, then automatically populates a target web form using Playwright. A human reviews the populated form before any submission.

## How It Works

```
Upload passport + G-28
        ↓
Extraction pipeline
  • Passport: LLM vision + MRZ checksum validation (when MRZ is valid, key fields are overridden at confidence=1.0)
  • G-28:     AcroForm widget extraction (fillable PDFs) → LLM vision fallback (scanned/image PDFs)
        ↓
Structured canonical output displayed in the UI
        ↓
Playwright opens the target form and fills all extracted fields
        ↓
Human reviews the populated form in the browser
(automation stops here — the form is never submitted)
```

The browser stays open after filling so the reviewer can inspect every field and catch any extraction errors before deciding to proceed.

---

## Setup

### 1. Create and activate the conda environment

```bash
conda env create -f environment.yml
conda activate alma
```

### 2. Install Playwright browsers

```bash
playwright install chromium
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY to your OpenAI API key
```

### 4. Run the backend

```bash
uvicorn backend.api.main:app --reload
```

### 5. Open the UI

Navigate to `http://localhost:8000`.

---

## Usage

1. **Upload passport** — drag and drop or click to select (JPEG or PNG)
2. **Extract Passport** — extracts beneficiary fields; extraction summary and raw output appear below
3. **Upload G-28** — drag and drop or click to select (PDF, JPEG, or PNG)
4. **Extract G-28** — extracts attorney fields; AcroForm is tried first, LLM vision is used as fallback
5. **Fill Form** — once both documents are extracted, this button opens Chromium and fills the target form automatically
6. **Review** — inspect the populated form in the browser; the form is never submitted automatically

---

## Extraction Details

### Passport
- LLM extracts all visual fields and the two raw MRZ lines
- MRZ lines are validated using checksum verification (TD3 format)
- If MRZ passes: key fields (passport number, name, dates, nationality, sex) are overridden with MRZ-derived values at confidence=1.0
- If MRZ fails: LLM visual values are used for all fields; failure is noted in the trace

### G-28
- For fillable PDFs: AcroForm widget annotations are read directly — no OCR needed
- For scanned or image-only PDFs: converted to JPEG and sent to LLM vision
- For image uploads: sent directly to LLM vision

### Trace
Each extraction response includes a `trace` object showing:
- `attempted_methods` — ordered list of methods tried (e.g. `["mrz", "llm_vision"]`)
- `final_method` — method whose output is used in the result
- `mrz_validation_passed` — (passport only) whether MRZ checksums passed
- `warnings` — processing-level notes

---

## Project Structure

```
backend/
  api/
    main.py            — FastAPI app: /extract/passport, /extract/g28, /fill
    test_harness.html  — Single-page UI served at /
  extraction/
    interface.py       — ExtractionResult dataclass and DocumentExtractor ABC
    llm_adapter.py     — OpenAIExtractor: passport and G-28 extraction
    mrz_extractor.py   — MRZ checksum validation (TD3 format)
    g28_acroform.py    — AcroForm widget extraction for fillable G-28 PDFs
    prompts.py         — LLM extraction prompts
  automation/
    form_filler.py     — Playwright form fill logic
docs/
  implementation-plan.md   — Phase-by-phase build plan
  schema-and-mapping.md    — Canonical schema and form field mapping table
example-input/             — Sample passport and G-28 files for testing
```

---

## Reliability and Validation

Extraction reliability is layered rather than assumed:

- **MRZ validation** — MRZ lines are only trusted if all TD3 checksums pass. If validation fails, MRZ values are discarded entirely and the visual extraction result is used. The failure is visible in the trace.
- **AcroForm preference** — For fillable G-28 PDFs, field values are read directly from widget annotations rather than parsed from visual text, eliminating OCR ambiguity for that path.
- **LLM fallback** — Used for image inputs and scanned PDFs where structured parsing is unavailable. LLM extraction is treated as lower-confidence and subject to verification.
- **Deterministic post-extraction verification** — After extraction, a lightweight rule-based pass checks for suspicious values (unexpected passport number format, date ordering violations, email format issues, missing bar number when licensing authority is present, and label contamination in name/address fields). Warnings are appended to affected field metadata and surfaced in the trace — extraction is never blocked.
- **Human review at the boundary** — Playwright automation stops after filling the form. The populated form stays open in the browser for a human to review before any submission.

---

## Evaluation

A lightweight field-level accuracy helper is included at `backend/evaluation/metrics.py` for checking extraction quality against known ground-truth values on the provided sample files.

```python
from backend.evaluation.metrics import compute_field_accuracy

result = compute_field_accuracy(
    expected={"last_name": "LEE", "passport_number": "M70689098"},
    extracted=beneficiary_section,
)
# {"correct_fields": 2, "total_fields": 2, "accuracy": 1.0, "mismatches": {}}
```

This is not a benchmarking framework — it is a minimal utility for spot-checking extraction output during development.

---

## Target Form

https://mendrika-alma.github.io/form-submission/

---

## Notes

- Poppler (`brew install poppler`) is only needed for the scanned PDF → LLM vision fallback path. The primary G-28 path (fillable PDFs via AcroForm) has no system dependencies beyond the conda environment.
- The LLM model is configurable via `LLM_MODEL` in `.env` (default: `gpt-4o-mini`).
- The `/fill` endpoint blocks until the user closes the browser, which is expected — the open browser is the review step.
