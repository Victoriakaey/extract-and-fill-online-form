import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from functools import partial
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from backend.automation.form_filler import fill_form
from backend.extraction.llm_adapter import OpenAIExtractor

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

if not os.getenv("LLM_API_KEY"):
    raise RuntimeError(
        "LLM_API_KEY is not set. Copy .env.example to .env and add your OpenAI API key."
    )


def _save_report(body: dict, fill_result: dict, autofill_time_ms: int) -> str:
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"report_{timestamp}_{uuid.uuid4().hex[:8]}.json"

    passport_resp = body.get("passport") or {}
    g28_resp      = body.get("g28") or {}
    passport_trace = passport_resp.get("trace") or {}
    g28_trace      = g28_resp.get("trace") or {}
    filled  = fill_result.get("filled", [])
    skipped = fill_result.get("skipped", [])
    errors  = fill_result.get("errors", [])

    passport_time_ms = passport_resp.get("extraction_time_ms", 0)
    g28_time_ms      = g28_resp.get("extraction_time_ms", 0)

    report = {
        "generated_at": datetime.now().isoformat(),
        "passport": passport_resp,
        "g28": g28_resp,
        "autofill": {
            "fields_with_values":    filled,
            "fields_without_values": skipped,
            "errors":                errors,
        },
        "pipeline_metrics": {
            "passport_extraction_time_ms": passport_time_ms,
            "g28_extraction_time_ms":      g28_time_ms,
            "autofill_time_ms":            autofill_time_ms,
            "total_time_ms":               passport_time_ms + g28_time_ms + autofill_time_ms,
        },
        "verification_checks": {
            "passport": passport_trace.get("verification_checks", []),
            "g28":      g28_trace.get("verification_checks", []),
        },
        "completion_metrics": {
            "fields_with_values":    len(filled),
            "fields_without_values": len(skipped),
            "processing_warnings":   len(passport_trace.get("warnings", [])) + len(g28_trace.get("warnings", [])),
            "verification_warnings": len(passport_trace.get("verification_warnings", [])) + len(g28_trace.get("verification_warnings", [])),
            "errors":                len(errors),
        },
        "status": {
            "passport_extraction_success": bool(passport_resp.get("data")),
            "g28_extraction_success":      bool(g28_resp.get("data")),
            "autofill_success":            len(errors) == 0,
        },
    }
    path.write_text(json.dumps(report, indent=2, default=str))
    return str(path)

app = FastAPI(title="Extraction Test Harness")

extractor = OpenAIExtractor()

ALLOWED_PASSPORT_TYPES = {"image/jpeg", "image/png"}
ALLOWED_G28_TYPES = {"application/pdf", "image/jpeg", "image/png"}

MAX_PASSPORT_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_G28_SIZE      = 20 * 1024 * 1024   # 20 MB


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "test_harness.html"
    return html_path.read_text()


@app.post("/extract/passport")
async def extract_passport(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_PASSPORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Accepted: JPEG, PNG.",
        )

    image_bytes = await file.read()
    if len(image_bytes) > MAX_PASSPORT_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_PASSPORT_SIZE // (1024*1024)} MB.")

    t0 = time.perf_counter()
    result = extractor.extract_passport(image_bytes)
    extraction_time_ms = round((time.perf_counter() - t0) * 1000)

    if not result.success:
        raise HTTPException(status_code=500, detail={"errors": result.errors})

    return {"data": result.data, "trace": result.trace, "extraction_time_ms": extraction_time_ms}


def _validate_fill_body(body: dict) -> None:
    """
    Validate that the /fill payload has the expected structure before running Playwright.
    Raises HTTPException(422) on any structural violation.
    """
    for section in ("passport", "g28"):
        if section not in body:
            raise HTTPException(status_code=422, detail=f"Missing required section: '{section}'")
        if not isinstance(body[section], dict):
            raise HTTPException(status_code=422, detail=f"'{section}' must be an object")
        data = body[section].get("data")
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail=f"'{section}.data' must be an object")
    beneficiary = body["passport"]["data"].get("beneficiary")
    if not isinstance(beneficiary, dict):
        raise HTTPException(status_code=422, detail="'passport.data.beneficiary' must be an object")
    attorney = body["g28"]["data"].get("attorney")
    if not isinstance(attorney, dict):
        raise HTTPException(status_code=422, detail="'g28.data.attorney' must be an object")


@app.post("/fill")
async def fill_form_endpoint(body: dict):
    """
    Open the target form in a browser and fill it from the canonical extraction object.

    Expects: {"passport": {"data": {"beneficiary": {...}}, "trace": ...},
              "g28":      {"data": {"attorney":    {...}}, "trace": ...}}

    Returns as soon as filling completes. The browser stays open in a background
    thread for human review. The form is never submitted.

    Design note: human review occurs after autofill (review-after-fill), not before.
    The populated browser form is the review artifact. There is no pre-fill editing
    step — corrections must be made directly in the browser or by re-running extraction.
    """
    _validate_fill_body(body)
    loop = asyncio.get_running_loop()
    try:
        t0 = time.perf_counter()
        result = await loop.run_in_executor(None, partial(fill_form, body))
        autofill_time_ms = round((time.perf_counter() - t0) * 1000)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    report_path = _save_report(body, result, autofill_time_ms)
    return {**result, "autofill_time_ms": autofill_time_ms, "report_path": report_path}


@app.post("/extract/g28")
async def extract_g28(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_G28_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Accepted: PDF, JPEG, PNG.",
        )

    document_bytes = await file.read()
    if len(document_bytes) > MAX_G28_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_G28_SIZE // (1024*1024)} MB.")

    t0 = time.perf_counter()
    result = extractor.extract_g28(document_bytes, file.content_type)
    extraction_time_ms = round((time.perf_counter() - t0) * 1000)

    if not result.success:
        raise HTTPException(status_code=500, detail={"errors": result.errors})

    return {"data": result.data, "trace": result.trace, "extraction_time_ms": extraction_time_ms}
