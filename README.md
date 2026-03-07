# Passport + G-28 Document Automation

A document automation prototype that extracts structured fields from a passport and a G-28 form, then uses browser automation to populate a target web form. The browser stays open after filling so a human can review the result before any submission.

<!-- **Target form:** https://mendrika-alma.github.io/form-submission/ -->

---

## What the System Does

```
User uploads passport + G-28
          │
          ▼
┌─────────────────────────────────────────────┐
│             Extraction Pipeline             │
│                                             │
│  Passport:                                  │
│    LLM vision → raw MRZ lines extracted     │
│    MRZ checksum validation (TD3)            │
│    If valid   → MRZ fields override LLM     │
│    If invalid → LLM visual values used      │
│                                             │
│  G-28 (PDF):                                │
│    AcroForm widget extraction (primary)     │
│    LLM vision fallback (scanned PDFs)       │
│                                             │
│  G-28 (image):                              │
│    LLM vision directly                      │
└─────────────────────────────────────────────┘
          │
          ▼
Canonical field objects (beneficiary + attorney)
          │
          ▼
┌─────────────────────────────────────────────┐
│          Verification Layer                 │
│  Deterministic rule checks on extracted     │
│  values. Warnings appended to fields.       │
│  Pipeline never blocked.                    │
└─────────────────────────────────────────────┘
          │
          ▼
UI shows extraction results + verification summary
          │
          ▼
┌─────────────────────────────────────────────┐
│         Playwright Form Automation          │
│  Browser opens → fields populated →         │
│  result returned immediately →              │
│  browser stays open for human review        │
│  Form is never submitted automatically.     │
└─────────────────────────────────────────────┘
          │
          ▼
Structured JSON report saved to reports/
```

---

## Setup

**Requirements:** Python 3.11+, conda, an OpenAI API key.

### 1. Create and activate the environment

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
```

Edit `.env` and set:

```
LLM_API_KEY=sk-...          # OpenAI API key (required)
LLM_MODEL=gpt-4o-mini       # Model to use (optional, default: gpt-4o-mini)
```

### 4. Run the server

```bash
uvicorn backend.api.main:app --reload
```

### 5. Open the UI

Navigate to `http://localhost:8000` in your browser.

> **Note:** Poppler (`brew install poppler`) is only needed for the scanned-PDF fallback path (PDF → JPEG → LLM vision). The primary G-28 path for fillable PDFs uses AcroForm extraction and has no system-level dependencies.

---

## Usage

1. **Upload passport** — drag and drop or click to select a JPEG or PNG passport image.
2. **Click Extract Passport** — the LLM extracts visual fields; MRZ checksum validation is attempted. The Extraction Summary shows which method produced the result, MRZ pass/fail status, and any processing or verification warnings.
3. **Upload G-28** — drag and drop or click to select a PDF, JPEG, or PNG G-28 form.
4. **Click Extract G-28** — AcroForm widget extraction is attempted first (for fillable PDFs); LLM vision is used as fallback.
5. **Review the Verification Summary** — appears once both documents are extracted. Shows a per-check pass/fail breakdown for each document before you proceed.
6. **Click Fill Form** — Chromium opens the target form and populates all extracted fields. The UI shows the autofill result as soon as filling completes.
7. **Review the populated form in the browser** — inspect every field. The form is never submitted automatically.

---

## Architecture

### Why different extraction strategies per document?

**Passport → LLM vision + MRZ validation**

Passports are image-only documents (no machine-readable structure in a PDF sense). The LLM extracts visual fields, including the raw MRZ lines. The MRZ zone encodes key fields with built-in checksums (TD3 format), so if the LLM extracts the MRZ lines correctly, checksum validation provides high-confidence field values. When MRZ validation fails, LLM visual values are used as-is with the failure noted in the trace.

**G-28 → AcroForm first, LLM vision fallback**

Fillable G-28 PDFs contain embedded AcroForm widget annotations — the actual values typed into form fields, not visual text. Reading these directly is more reliable than OCR or LLM vision. This path requires no external API calls and returns exact values. Scanned or image-only PDFs fall back to LLM vision.

**LLM as fallback, not primary**

LLM vision is used where deterministic methods are unavailable or fail. It is treated as lower-confidence output and always passed through the verification layer.

### Verification layer

Runs after extraction, before returning results. Checks are deterministic and rule-based. Warnings are appended to affected field metadata and to the trace. The pipeline never blocks on a verification warning — the intent is to surface issues for human review, not to hard-fail.

### Human review boundary

Playwright fills the form and stops. The browser stays open. The populated form is the human review step. No submission happens automatically.

### Report

After autofill, a timestamped JSON report is written to `reports/`. It captures the full extraction output, trace, verification check results, autofill summary, and pipeline timing metrics.

---

## Project Structure

```
backend/
  api/
    main.py              FastAPI application. Endpoints: GET /, POST /extract/passport,
                         POST /extract/g28, POST /fill. Handles timing, report saving.
    test_harness.html    Single-page UI. Extraction, verification summary, autofill
                         trigger, and result display. Served at /.

  extraction/
    interface.py         ExtractionResult dataclass and DocumentExtractor ABC.
                         Defines the contract between extractors and the API layer.
    llm_adapter.py       OpenAIExtractor. Implements passport and G-28 extraction,
                         MRZ override logic, and wires in verification.
    mrz_extractor.py     TD3 MRZ checksum validation. Returns canonical field overrides
                         when checksums pass, None when they fail.
    g28_acroform.py      AcroForm widget extraction for fillable G-28 PDFs. Two-pass:
                         name-based field mapping, then value-type validation/relocation.
    prompts.py           LLM extraction prompts for passport and G-28.
    verification.py      Deterministic post-extraction checks. Returns per-check
                         pass/warning results and warning strings for the trace.

  automation/
    form_filler.py       Playwright form fill. Runs browser in a background thread,
                         returns the fill result as soon as filling completes (browser
                         stays open independently for human review).

  evaluation/
    metrics.py           Offline utility: compute_field_accuracy(expected, extracted).
                         Not used in the live pipeline — for spot-checking against
                         known sample values during development.

docs/
  schema-and-mapping.md  Canonical schema definition and form field selector mapping.
  implementation-plan.md Phase-by-phase build plan (reference only).

example-input/           Sample passport and G-28 files for local testing.

reports/                 Auto-generated timestamped JSON reports (one per autofill run).
```

---

## Canonical Schema

Each extracted field follows this shape:

```json
{
  "value":      "LEE",
  "confidence": 0.95,
  "source":     "passport",
  "warnings":   []
}
```

- `value` — extracted string, or `null` if absent
- `confidence` — LLM self-reported estimate (0–1), or `1.0` for MRZ/AcroForm values, or `null` when value is null
- `source` — always `"passport"` or `"g28"`, injected by the adapter (never by the model)
- `warnings` — field-level notes from extraction or verification

The full canonical object has two top-level sections: `beneficiary` (passport fields) and `attorney` (G-28 fields). See `docs/schema-and-mapping.md` for the complete schema and form selector mapping.

---

## Observability

### Trace

Every extraction response includes a `trace` object:

```json
{
  "attempted_methods":      ["mrz", "llm_vision"],
  "final_method":           "llm_vision",
  "mrz_validation_passed":  false,
  "warnings":               ["MRZ validation failed — using LLM visual values",
                             "MRZ lines wrong length — line1=43 chars, line2=40 chars (expected 44 each)"],
  "mrz_raw":                {"line1": "...", "line2": "..."},
  "verification_warnings":  [],
  "verification_checks":    [
    {"check": "passport_number_format", "status": "pass"},
    {"check": "sex_value",              "status": "pass"},
    {"check": "date_ordering",          "status": "pass"}
  ]
}
```

### Saved report

After every autofill run, `reports/report_<timestamp>.json` is written. It contains:

- `passport` / `g28` — full extraction response (data + trace)
- `verification_checks` — per-check pass/warning results for both documents
- `autofill` — fields with values, fields without values, errors
- `pipeline_metrics` — per-stage timing (extraction, autofill, total)
- `completion_metrics` — field counts, warning counts, error count
- `status` — extraction and autofill success flags

---

## Reliability and Validation

- **Structured-source-first** — AcroForm and MRZ are preferred over LLM vision wherever available. They produce deterministic output with no OCR ambiguity.
- **MRZ validation** — MRZ field values are only used when all TD3 checksums pass. A failed MRZ is fully discarded; it is never used to derive partial field values.
- **Verification layer** — Runs post-extraction. Checks: passport number format, date ordering, sex value, email format, ZIP format, bar number / licensing authority consistency, label contamination in name fields. All results are recorded. Warnings surface to the UI and report; none block the pipeline.
- **Warnings over hard failures** — The system is designed to proceed and surface issues rather than fail silently or block the user. A reviewer sees exactly what was flagged and can make the final call.
- **Human review at the boundary** — The populated browser form is the review step. The user sees the exact values that will be submitted before making any decision.

---

## Limitations

- **MRZ extraction accuracy** — LLM vision is not reliably accurate at character level for 44-character fixed-width MRZ strings. MRZ validation catches errors, but when it fails, the system falls back to LLM visual values, which may themselves be imprecise.
- **LLM visual extraction variability** — For image-based inputs, field extraction quality depends on image resolution, lighting, and model performance. Low-confidence or missing values are flagged but not corrected automatically.
- **Verification is lightweight** — The verification layer applies simple deterministic rules. It will not catch all extraction errors — it can only flag values that match specific suspicious patterns.
- **No editable review UI** — There is no intermediate screen for editing extracted values before autofill. Human review happens on the final populated form in the browser. Corrections require re-running extraction or manual edits in the form itself.
- **Prototype scope** — This is a take-home assignment implementation. It is not production-hardened: there is no authentication, no persistent storage, no concurrent session handling, and no retry logic for API failures.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Structured parsing before LLM | AcroForm and MRZ are deterministic and higher-accuracy. LLM is the fallback, not the default. |
| MRZ all-or-nothing | A partially valid MRZ is not reliable. Full checksum validation is required before any MRZ-derived value is used. |
| Warnings instead of blocking | Extraction errors are often partial. Blocking on any warning would prevent autofill even when most fields are correct. Human review is the final gate. |
| Browser stays open | The populated form is the review artifact. Closing it automatically would remove the review step the assignment requires. |
| Result returned before browser close | The autofill thread signals completion via a queue as soon as filling ends. The browser lifecycle continues independently, so the UI is not blocked waiting for the user to close the window. |
| Pipeline metrics at runtime | Timing and completeness metrics are observable facts about the current run. Ground-truth accuracy metrics are not computed in the live flow because there is no ground truth for arbitrary uploads. |
| JSON report as run artifact | Captures the full state of a run (extraction, verification, autofill, timing) for debugging and review without requiring a persistent database. |
