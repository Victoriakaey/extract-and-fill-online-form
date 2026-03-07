# Passport + G-28 Document Automation System

Uploads a passport and G-28 form, extracts structured data using an LLM, presents it for human review, and autofills a target web form using Playwright.

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
# Edit .env and add your OpenAI API key
```

### 4. Run the backend

```bash
uvicorn backend.api.main:app --reload
```

### 5. Open the test harness

Navigate to `http://localhost:8000` in your browser to test document extraction.

---

## Optional: Poppler (scanned PDF fallback only)

Poppler is **not required** for the primary extraction path.

The primary G-28 path uses `pdfplumber` to extract text from fillable PDFs — no system dependencies needed.

Poppler is only needed if you want to support the LLM vision fallback for scanned/image-only PDFs:

```bash
brew install poppler
```

---

## Project Structure

```
backend/
  extraction/   — LLM extraction service
  api/          — FastAPI app and endpoints
  automation/   — Playwright autofill service
frontend/       — React app (Phase 3)
tests/          — Validation and smoke test scripts
```

## Target Form

https://mendrika-alma.github.io/form-submission/
