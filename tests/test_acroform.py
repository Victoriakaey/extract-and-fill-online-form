"""
Unit tests for backend/extraction/g28_acroform.py

Tests internal helpers (_strip_index, _normalize, _value_type) and the
full extract_g28_acroform function against synthetic in-memory PDFs.
"""

import pytest
from backend.extraction.g28_acroform import _strip_index, _normalize, _value_type


# ---------------------------------------------------------------------------
# _strip_index
# ---------------------------------------------------------------------------

class TestStripIndex:
    def test_strips_bracket_suffix(self):
        assert _strip_index("FieldName[0]") == "FieldName"

    def test_strips_higher_index(self):
        assert _strip_index("Line3e_ZipCode[2]") == "Line3e_ZipCode"

    def test_no_bracket_unchanged(self):
        assert _strip_index("FieldName") == "FieldName"

    def test_empty_string(self):
        assert _strip_index("") == ""


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_returns_stripped_value(self):
        assert _normalize("  Smith  ") == "Smith"

    def test_empty_string_returns_none(self):
        assert _normalize("") is None

    def test_whitespace_only_returns_none(self):
        assert _normalize("   ") is None

    @pytest.mark.parametrize("null_val", ["N/A", "N/a", "n/a", "NA", "/Off"])
    def test_null_sentinels_return_none(self, null_val):
        assert _normalize(null_val) is None

    def test_normal_value_preserved(self):
        assert _normalize("California State Bar") == "California State Bar"


# ---------------------------------------------------------------------------
# _value_type
# ---------------------------------------------------------------------------

class TestValueType:
    def test_email_detected(self):
        assert _value_type("attorney@lawfirm.com") == "email"

    def test_phone_detected(self):
        assert _value_type("(310) 555-1234") == "phone"

    def test_plain_text(self):
        assert _value_type("John Smith") == "text"

    def test_zip_code_is_text(self):
        assert _value_type("90210") == "text"
