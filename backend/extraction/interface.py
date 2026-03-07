from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    """
    Wrapper for extraction output at the service boundary.

    data: partial canonical schema object.
      - passport extraction returns {"beneficiary": {field: {value, confidence, source, warnings}}}
      - G-28 extraction returns    {"attorney":    {field: {value, confidence, source, warnings}}}

    The backend composition layer is responsible for merging these into the full canonical object.

    trace: lightweight processing summary for debugging and UI display.
      - attempted_methods: ordered list of methods tried, e.g. ["mrz", "llm_vision"]
      - final_method: the method whose output is actually used in the result
          "mrz"        — MRZ checksum validation succeeded; key fields come from MRZ
          "acroform"   — PDF AcroForm widget extraction succeeded
          "llm_vision" — LLM multimodal extraction (used as primary or after fallback)
      - mrz_validation_passed: bool (passport only) — whether MRZ checksums passed
      - warnings: list of processing-level notes (not field-level warnings)

    Note: confidence values are lightweight review aids only — not calibrated probability scores.
    """
    data: dict
    success: bool
    errors: list = field(default_factory=list)
    trace: dict = field(default_factory=dict)


class DocumentExtractor(ABC):

    @abstractmethod
    def extract_passport(self, image_bytes: bytes) -> ExtractionResult:
        """
        Extract beneficiary fields from a passport image.

        Returns partial canonical object:
            {"beneficiary": {field_name: {value, confidence, source, warnings}}}

        source is always "passport" — injected by the adapter, not the model.
        """
        ...

    @abstractmethod
    def extract_g28(self, document_bytes: bytes, mime_type: str) -> ExtractionResult:
        """
        Extract attorney fields from a G-28 document.

        Args:
            document_bytes: raw file bytes
            mime_type: "image/jpeg", "image/png", or "application/pdf"

        Returns partial canonical object:
            {"attorney": {field_name: {value, confidence, source, warnings}}}

        source is always "g28" — injected by the adapter, not the model.
        """
        ...
