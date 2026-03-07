import asyncio
from functools import partial
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from backend.automation.form_filler import fill_form
from backend.extraction.llm_adapter import OpenAIExtractor

app = FastAPI(title="Extraction Test Harness")

extractor = OpenAIExtractor()

ALLOWED_PASSPORT_TYPES = {"image/jpeg", "image/png"}
ALLOWED_G28_TYPES = {"application/pdf", "image/jpeg", "image/png"}


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
    result = extractor.extract_passport(image_bytes)

    if not result.success:
        raise HTTPException(status_code=500, detail={"errors": result.errors})

    return {"data": result.data, "trace": result.trace}


@app.post("/fill")
async def fill_form_endpoint(body: dict):
    """
    Open the target form in a browser and fill it from the canonical extraction object.

    Expects: {"beneficiary": {...}, "attorney": {...}}

    The browser stays open after filling so the user can review the fields.
    The form is never submitted. This call blocks until the user closes the browser.
    """
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, partial(fill_form, body))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/extract/g28")
async def extract_g28(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_G28_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Accepted: PDF, JPEG, PNG.",
        )

    document_bytes = await file.read()
    result = extractor.extract_g28(document_bytes, file.content_type)

    if not result.success:
        raise HTTPException(status_code=500, detail={"errors": result.errors})

    return {"data": result.data, "trace": result.trace}
