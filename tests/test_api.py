"""
API smoke tests for backend/api/main.py

Tests input validation and error handling without making real LLM calls.
Requires the FastAPI app to be importable but does NOT require a running server
or a valid LLM_API_KEY (validation errors are caught before any LLM call).
"""

import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("LLM_API_KEY", "test-key-for-validation-tests")

from backend.api.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# /extract/passport — content-type validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_passport_rejects_pdf(client):
    response = await client.post(
        "/extract/passport",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_passport_rejects_oversized_file(client):
    big = b"x" * (11 * 1024 * 1024)  # 11 MB
    response = await client.post(
        "/extract/passport",
        files={"file": ("photo.jpg", big, "image/jpeg")},
    )
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# /extract/g28 — content-type validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g28_rejects_unsupported_type(client):
    response = await client.post(
        "/extract/g28",
        files={"file": ("doc.docx", b"PK", "application/vnd.openxmlformats-officedocument")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_g28_rejects_oversized_file(client):
    big = b"x" * (21 * 1024 * 1024)  # 21 MB
    response = await client.post(
        "/extract/g28",
        files={"file": ("form.pdf", big, "application/pdf")},
    )
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# /fill — body validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fill_rejects_empty_body(client):
    response = await client.post("/fill", json={})
    assert response.status_code == 422
    assert "passport" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fill_rejects_wrong_section_type(client):
    response = await client.post("/fill", json={"passport": "string", "g28": {}})
    assert response.status_code == 422
    assert "'passport' must be an object" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fill_rejects_missing_data(client):
    response = await client.post("/fill", json={"passport": {}, "g28": {}})
    assert response.status_code == 422
    assert "data" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fill_rejects_missing_beneficiary(client):
    response = await client.post("/fill", json={
        "passport": {"data": {}},
        "g28":      {"data": {"attorney": {}}},
    })
    assert response.status_code == 422
    assert "beneficiary" in response.json()["detail"]
