import base64
import json
import os
from io import BytesIO

from dotenv import load_dotenv
from openai import OpenAI
from pdf2image import convert_from_bytes

from .g28_acroform import extract_g28_acroform
from .interface import DocumentExtractor, ExtractionResult
from .mrz_extractor import parse_mrz
from .prompts import PASSPORT_EXTRACTION_PROMPT, G28_EXTRACTION_PROMPT
from .verification import verify_passport_fields, verify_g28_fields

load_dotenv()

PASSPORT_FIELDS = [
    "last_name", "first_name", "middle_name", "passport_number", "country_of_issue",
    "nationality", "date_of_birth", "place_of_birth", "sex", "date_of_issue", "date_of_expiration",
]

G28_FIELDS = [
    "online_account_number", "last_name", "first_name", "middle_name",
    "street_address", "apt_ste_flr_type", "apt_ste_flr_number", "city", "state", "zip_code", "country",
    "daytime_phone", "mobile_phone", "email",
    "licensing_authority", "bar_number", "subject_to_restrictions", "firm_name",
]


def _build_canonical_section(raw: dict, fields: list, source: str) -> dict:
    """
    Convert flat LLM output into canonical field metadata.
    source is injected deterministically — the model never produces it.
    confidence is always null when value is null.
    """
    result = {}
    for field_name in fields:
        entry = raw.get(field_name)
        if isinstance(entry, dict):
            value = entry.get("value")
            result[field_name] = {
                "value": value,
                "confidence": entry.get("confidence") if value is not None else None,
                "source": source,
                "warnings": entry.get("warnings", []),
            }
        else:
            result[field_name] = {
                "value": None,
                "confidence": None,
                "source": source,
                "warnings": ["field missing from model response"],
            }
    return result


def _to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    """
    Convert first page of PDF to JPEG bytes for LLM vision input.
    Used only when AcroForm extraction fails (scanned/non-fillable PDF fallback).
    V1.5: this path may be replaced by pdfplumber structured parsing.
    """
    images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1)
    buf = BytesIO()
    images[0].save(buf, format="JPEG")
    return buf.getvalue()


class OpenAIExtractor(DocumentExtractor):

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("LLM_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    def _call_vision(self, prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        b64 = _to_base64(image_bytes)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1200,
        )
        return json.loads(response.choices[0].message.content)

    def extract_passport(self, image_bytes: bytes) -> ExtractionResult:
        """
        Passport extraction:
          1. LLM extracts visual fields + raw MRZ lines from the image.
          2. MRZ lines validated with checksum (mrz library).
          3. If valid → MRZ-derived values override key fields at confidence=1.0.
          4. LLM visual values remain for non-MRZ fields (place_of_birth,
             date_of_issue, middle_name).
        """
        try:
            raw = self._call_vision(PASSPORT_EXTRACTION_PROMPT, image_bytes)
            beneficiary = _build_canonical_section(raw, PASSPORT_FIELDS, source="passport")

            mrz_line1 = raw.get("mrz_line1", "")
            mrz_line2 = raw.get("mrz_line2", "")
            mrz_overrides = parse_mrz(mrz_line1, mrz_line2)

            if mrz_overrides:
                for field_name, mrz_value in mrz_overrides.items():
                    if mrz_value is not None:
                        beneficiary[field_name] = {
                            "value": mrz_value,
                            "confidence": 1.0,
                            "source": "passport",
                            "warnings": [],
                        }
                trace = {
                    "attempted_methods": ["mrz"],
                    "final_method": "mrz",
                    "mrz_validation_passed": True,
                    "warnings": [],
                    "mrz_raw": {"line1": mrz_line1, "line2": mrz_line2},
                }
            else:
                mrz_warnings = ["MRZ validation failed — using LLM visual values"]
                l1, l2 = len(mrz_line1), len(mrz_line2)
                if l1 != 44 or l2 != 44:
                    mrz_warnings.append(
                        f"MRZ lines wrong length — line1={l1} chars, line2={l2} chars (expected 44 each)"
                    )
                else:
                    mrz_warnings.append("MRZ lines correct length — checksum validation failed")
                trace = {
                    "attempted_methods": ["mrz", "llm_vision"],
                    "final_method": "llm_vision",
                    "mrz_validation_passed": False,
                    "warnings": mrz_warnings,
                    "mrz_raw": {"line1": mrz_line1, "line2": mrz_line2},
                }

            verification_warnings = verify_passport_fields(beneficiary)
            trace["verification_warnings"] = verification_warnings

            return ExtractionResult(data={"beneficiary": beneficiary}, success=True, trace=trace)
        except Exception as e:
            return ExtractionResult(
                data={"beneficiary": {}},
                success=False,
                errors=[str(e)],
            )

    def extract_g28(self, document_bytes: bytes, mime_type: str) -> ExtractionResult:
        """
        G-28 extraction strategy:
          1. If PDF: try AcroForm widget extraction first (direct, reliable).
             If sufficient fields recovered → return AcroForm result.
             If not (scanned/non-fillable PDF) → fall back to LLM vision.
          2. If image: send directly to LLM vision.
        """
        try:
            if mime_type == "application/pdf":
                attorney = extract_g28_acroform(document_bytes)
                if attorney is not None:
                    trace = {
                        "attempted_methods": ["acroform"],
                        "final_method": "acroform",
                        "warnings": [],
                        "verification_warnings": verify_g28_fields(attorney),
                    }
                    return ExtractionResult(data={"attorney": attorney}, success=True, trace=trace)
                # AcroForm extraction failed — fall back to LLM vision
                image_bytes = _pdf_to_image_bytes(document_bytes)
                image_mime = "image/jpeg"
                trace = {
                    "attempted_methods": ["acroform", "llm_vision"],
                    "final_method": "llm_vision",
                    "warnings": ["AcroForm extraction failed — fell back to LLM vision"],
                }
            else:
                image_bytes = document_bytes
                image_mime = mime_type
                trace = {
                    "attempted_methods": ["llm_vision"],
                    "final_method": "llm_vision",
                    "warnings": [],
                }

            raw = self._call_vision(G28_EXTRACTION_PROMPT, image_bytes, image_mime)
            attorney = _build_canonical_section(raw, G28_FIELDS, source="g28")
            trace["verification_warnings"] = verify_g28_fields(attorney)
            return ExtractionResult(data={"attorney": attorney}, success=True, trace=trace)
        except Exception as e:
            return ExtractionResult(
                data={"attorney": {}},
                success=False,
                errors=[str(e)],
            )
