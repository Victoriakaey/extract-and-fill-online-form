# Passport + G-28 Document Automation

Extracts structured fields from a passport and a G-28 attorney form, then uses browser automation to populate a target web form. The browser stays open after filling for human review. No submission occurs automatically.

---

## Quick Overview

| What | How |
|---|---|
| Passport extraction | LLM vision + MRZ checksum validation (TD3) |
| G-28 extraction | AcroForm widget parsing (fillable PDFs) or LLM vision fallback (scanned/image) |
| Post-extraction | Deterministic verification checks; warnings surface to UI and report |
| Form fill | Playwright opens Chromium, fills all mapped fields, returns result immediately |
| Human review | Browser stays open; populated form is the review artifact |
| Output | Timestamped JSON report in `reports/` after every autofill run |

---

## Pipeline

```
Upload passport + G-28
        │
        ▼
┌────────────────────────────────────┐
│         Extraction                 │
│                                    │
│  Passport:                         │
│    LLM vision → raw MRZ lines      │
│    TD3 checksum validation         │
│    Pass → MRZ values override LLM  │
│    Fail → LLM visual values used   │
│                                    │
│  G-28 (PDF):                       │
│    AcroForm widget extraction      │
│    LLM vision fallback if needed   │
│                                    │
│  G-28 (image):                     │
│    LLM vision directly             │
└────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────┐
│         Verification               │
│  Rule-based checks on extracted    │
│  values. Appends warnings to       │
│  fields. Never blocks pipeline.    │
└────────────────────────────────────┘
        │
        ▼
UI shows extraction results + verification summary
        │
        ▼
┌────────────────────────────────────┐
│         Form Automation            │
│  Playwright fills form →           │
│  result returned immediately →     │
│  browser stays open for review     │
└────────────────────────────────────┘
        │
        ▼
JSON report saved to reports/
```

---

## Architecture

### Extraction strategy

**Structured sources before LLM — always.**

For the G-28, fillable PDFs contain embedded AcroForm widget annotations — the actual typed values, not rendered text. Reading these directly is more reliable than any vision-based approach: no OCR error surface, no API call, deterministic output. LLM vision is only invoked when AcroForm extraction yields nothing (scanned or image-only PDFs).

For the passport, AcroForm doesn't apply. The LLM extracts visual fields and the raw MRZ lines. The MRZ zone encodes key fields with built-in TD3 checksums. When all checksums pass, MRZ-derived values override LLM visual values at `confidence: 1.0`. When any checksum fails, the MRZ is discarded entirely — no partial values are derived from a failed MRZ. LLM visual values are used as-is with the failure recorded in the trace.

**Why all-or-nothing on MRZ?** A partially valid MRZ is not trustworthy. Either every checksum passes and the MRZ is reliable, or it failed and shouldn't be used at all. Mixing MRZ-derived and visually-extracted values for the same document without a clear confidence model creates silent errors.

### Verification layer

Runs post-extraction on every response. Checks are deterministic and rule-based — format validation, date ordering, cross-field consistency (e.g., bar number present ↔ licensing authority present). Each check records a `pass` or `warning` result with a message. Warnings append to affected field metadata and to the trace. The pipeline never blocks on a verification warning — surfacing issues for human review is the intent, not hard-failing on ambiguous data.

### Human review boundary

Playwright fills the form and stops. The browser stays open. The populated form is the review step — the user sees the exact values before deciding whether to submit. The `fill_form` function uses a thread-and-queue pattern: the fill thread signals completion via a `queue.Queue` as soon as field population ends, then waits for browser close independently. The HTTP response is returned immediately without blocking on browser lifecycle.

---

## Canonical Schema

Every extracted field follows this shape:

```json
{
  "value":      "LEE",
  "confidence": 0.95,
  "source":     "passport",
  "warnings":   []
}
```

- `value` — extracted string, or `null` if absent
- `confidence` — LLM self-reported (0–1), `1.0` for MRZ/AcroForm, `null` when value is null
- `source` — `"passport"` or `"g28"`, injected by the adapter (never by the model)
- `warnings` — field-level notes from extraction or verification

The full canonical object has two sections: `beneficiary` (passport fields) and `attorney` (G-28 fields).

---

## Observability

### Trace

Every extraction response includes a `trace` object:

```json
{
  "attempted_methods":     ["mrz", "llm_vision"],
  "final_method":          "llm_vision",
  "mrz_validation_passed": false,
  "warnings":              ["MRZ validation failed — using LLM visual values",
                            "MRZ lines wrong length — line1=43 chars, line2=40 chars (expected 44 each)"],
  "mrz_raw":               {"line1": "...", "line2": "..."},
  "verification_warnings": [],
  "verification_checks": [
    {"check": "passport_number_format", "status": "pass"},
    {"check": "sex_value",              "status": "pass"},
    {"check": "date_ordering",          "status": "pass"}
  ]
}
```

`attempted_methods` is in chronological order. `final_method` is the source of the returned field values.

### Report

After every autofill run, `reports/report_<timestamp>.json` captures:

- `passport` / `g28` — full extraction response (data + trace)
- `verification_checks` — per-check pass/warning for both documents
- `autofill` — fields filled, fields skipped (null value), errors
- `pipeline_metrics` — per-stage timing: extraction, autofill, total
- `completion_metrics` — field counts, warning counts, error count
- `status` — extraction and autofill success flags

---

## Project Structure

```
backend/
  api/
    main.py              FastAPI app. Endpoints: GET /, POST /extract/passport,
                         POST /extract/g28, POST /fill. Handles timing, report saving.
    test_harness.html    Single-page UI. Extraction, verification summary, autofill
                         trigger, result display. Served at /.

  extraction/
    interface.py         ExtractionResult dataclass + DocumentExtractor ABC.
    llm_adapter.py       OpenAIExtractor. Passport and G-28 extraction, MRZ override
                         logic, verification wiring.
    mrz_extractor.py     TD3 MRZ checksum validation. Returns field overrides on pass,
                         None on fail.
    g28_acroform.py      AcroForm widget extraction for fillable PDFs. Two-pass:
                         name-based field mapping, then value-type validation.
    prompts.py           LLM extraction prompts for passport and G-28.
    verification.py      Deterministic post-extraction checks. Returns per-check
                         pass/warning results and warning strings.

  automation/
    form_filler.py       Playwright form fill. Thread-and-queue pattern: returns fill
                         result immediately; browser stays open in daemon thread.

  evaluation/
    metrics.py           Offline utility: compute_field_accuracy(expected, extracted).
                         Not used in live pipeline.

docs/
  schema-and-mapping.md  Canonical schema and form field selector mapping.
  implementation-plan.md Build plan (reference only).

example-input/           Sample passport and G-28 files for local testing.
reports/                 Auto-generated JSON reports (one per autofill run).
```

---

## Setup

**Requirements:** Python 3.11+, conda, OpenAI API key.

```bash
# 1. Create environment
conda env create -f environment.yml
conda activate alma

# 2. Install Playwright browser
playwright install chromium

# 3. Configure environment
cp .env.example .env
# Set LLM_API_KEY=sk-... in .env

# 4. Start server
uvicorn backend.api.main:app --reload

# 5. Open UI
# Navigate to http://localhost:8000
```

> **Note:** `brew install poppler` is only needed for the scanned-PDF fallback path (PDF → JPEG → LLM vision). The primary path for fillable G-28 PDFs uses AcroForm extraction and has no system dependencies.

---

## Usage

1. Upload a passport image (JPEG or PNG) and click **Extract Passport**.
2. Upload a G-28 (PDF, JPEG, or PNG) and click **Extract G-28**.
3. Review the **Verification Summary** — per-check pass/fail for each document.
4. Click **Fill Form** — Chromium opens and populates all mapped fields.
5. Review the populated form in the browser. The form is never submitted automatically.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Structured extraction before LLM | AcroForm and MRZ are deterministic and higher-accuracy. LLM is the fallback, not the default. |
| MRZ all-or-nothing | A partially valid MRZ is not trustworthy. Full checksum validation required before any MRZ value is used. |
| Warnings over blocking | Extraction errors are often partial. Blocking on any warning would prevent autofill even when most fields are correct. Human review is the final gate. |
| Browser stays open | The populated form is the review artifact. Closing it automatically removes the required human review step. |
| Fill result before browser close | The fill thread signals via queue as soon as filling ends. Browser lifecycle continues independently so the API response is not blocked. |
| Per-stage timing at runtime | Timing and completeness are observable facts of each run. Ground-truth accuracy is not computed in the live flow — there is no ground truth for arbitrary uploads. |
| JSON report as run artifact | Captures full state (extraction, verification, autofill, timing) for debugging and audit without requiring a database. |

---

## Limitations

- **MRZ extraction accuracy** — LLM vision is not reliably character-accurate for 44-character fixed-width MRZ strings. When MRZ validation fails, the system falls back to LLM visual values, which may themselves be imprecise for low-resolution images.
- **LLM visual extraction variability** — Field quality depends on image resolution, lighting, and model performance. Low-confidence or missing values are flagged but not corrected.
- **Verification coverage** — The verification layer applies lightweight deterministic rules. It will not catch all extraction errors — only values that match specific suspicious patterns.
- **No editable review UI** — There is no intermediate step to edit extracted values before autofill. Corrections require re-running extraction or editing the form directly in the browser.
- **Prototype scope** — No authentication, persistent storage, concurrent session handling, or API retry logic.
