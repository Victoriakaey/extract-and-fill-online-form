"""
Unit tests for backend/extraction/verification.py

Tests verify_passport_fields and verify_g28_fields independently of the LLM
or any file I/O. All inputs are constructed inline.
"""

import pytest
from backend.extraction.verification import verify_passport_fields, verify_g28_fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _field(value, confidence=0.9):
    return {"value": value, "confidence": confidence, "source": "passport", "warnings": []}


def _g28_field(value, confidence=0.9):
    return {"value": value, "confidence": confidence, "source": "g28", "warnings": []}


def _check_status(result, check_name):
    for c in result["checks"]:
        if c["check"] == check_name:
            return c["status"]
    return None


# ---------------------------------------------------------------------------
# verify_passport_fields
# ---------------------------------------------------------------------------

class TestPassportNumberFormat:
    def test_valid_alphanumeric_passes(self):
        data = {"passport_number": _field("M70689090")}
        result = verify_passport_fields(data)
        assert _check_status(result, "passport_number_format") == "pass"

    def test_ten_char_passes(self):
        data = {"passport_number": _field("M706890908")}
        result = verify_passport_fields(data)
        assert _check_status(result, "passport_number_format") == "pass"

    def test_lowercase_warns(self):
        data = {"passport_number": _field("m70689090")}
        result = verify_passport_fields(data)
        assert _check_status(result, "passport_number_format") == "warning"

    def test_special_chars_warn(self):
        data = {"passport_number": _field("M706-890")}
        result = verify_passport_fields(data)
        assert _check_status(result, "passport_number_format") == "warning"

    def test_too_short_warns(self):
        data = {"passport_number": _field("M123")}
        result = verify_passport_fields(data)
        assert _check_status(result, "passport_number_format") == "warning"

    def test_null_value_skips_check(self):
        data = {"passport_number": _field(None, confidence=None)}
        result = verify_passport_fields(data)
        assert _check_status(result, "passport_number_format") is None


class TestSexValue:
    @pytest.mark.parametrize("sex", ["M", "F", "X"])
    def test_valid_values_pass(self, sex):
        data = {"sex": _field(sex)}
        result = verify_passport_fields(data)
        assert _check_status(result, "sex_value") == "pass"

    def test_lowercase_warns(self):
        data = {"sex": _field("m")}
        result = verify_passport_fields(data)
        assert _check_status(result, "sex_value") == "warning"

    def test_unexpected_value_warns(self):
        data = {"sex": _field("MALE")}
        result = verify_passport_fields(data)
        assert _check_status(result, "sex_value") == "warning"


class TestDateOrdering:
    def test_correct_ordering_passes(self):
        data = {
            "date_of_birth":      _field("1985-07-02"),
            "date_of_issue":      _field("2014-04-15"),
            "date_of_expiration": _field("2024-04-15"),
        }
        result = verify_passport_fields(data)
        assert _check_status(result, "date_ordering") == "pass"

    def test_wrong_ordering_warns(self):
        data = {
            "date_of_birth":      _field("1985-07-02"),
            "date_of_issue":      _field("2024-04-15"),
            "date_of_expiration": _field("2014-04-15"),  # expiry before issue
        }
        result = verify_passport_fields(data)
        assert _check_status(result, "date_ordering") == "warning"

    def test_missing_one_date_warns(self):
        data = {
            "date_of_birth":      _field("1985-07-02"),
            "date_of_issue":      _field("2014-04-15"),
            "date_of_expiration": _field(None, confidence=None),
        }
        result = verify_passport_fields(data)
        assert _check_status(result, "date_ordering") == "warning"
        assert any("missing" in w for w in result["warnings"])

    def test_all_dates_null_skips_check(self):
        data = {
            "date_of_birth":      _field(None, confidence=None),
            "date_of_issue":      _field(None, confidence=None),
            "date_of_expiration": _field(None, confidence=None),
        }
        result = verify_passport_fields(data)
        assert _check_status(result, "date_ordering") is None

    def test_warning_appended_to_field_metadata(self):
        data = {
            "date_of_birth":      _field("1985-07-02"),
            "date_of_issue":      _field("2024-04-15"),
            "date_of_expiration": _field("2014-04-15"),
        }
        verify_passport_fields(data)
        assert len(data["date_of_birth"]["warnings"]) > 0


# ---------------------------------------------------------------------------
# verify_g28_fields
# ---------------------------------------------------------------------------

class TestEmailFormat:
    def test_valid_email_passes(self):
        data = {"email": _g28_field("attorney@lawfirm.com")}
        result = verify_g28_fields(data)
        assert _check_status(result, "email_format") == "pass"

    def test_invalid_email_warns(self):
        data = {"email": _g28_field("not-an-email")}
        result = verify_g28_fields(data)
        assert _check_status(result, "email_format") == "warning"

    def test_null_email_skips_check(self):
        data = {"email": _g28_field(None, confidence=None)}
        result = verify_g28_fields(data)
        assert _check_status(result, "email_format") is None


class TestZipCodeFormat:
    def test_five_digit_passes(self):
        data = {"zip_code": _g28_field("90210")}
        result = verify_g28_fields(data)
        assert _check_status(result, "zip_code_format") == "pass"

    def test_zip_plus_four_passes(self):
        data = {"zip_code": _g28_field("90210-1234")}
        result = verify_g28_fields(data)
        assert _check_status(result, "zip_code_format") == "pass"

    def test_letters_warn(self):
        data = {"zip_code": _g28_field("9021O")}  # letter O not zero
        result = verify_g28_fields(data)
        assert _check_status(result, "zip_code_format") == "warning"


class TestBarNumberConsistency:
    def test_both_present_passes(self):
        data = {
            "licensing_authority": _g28_field("California State Bar"),
            "bar_number":          _g28_field("123456"),
        }
        result = verify_g28_fields(data)
        assert _check_status(result, "bar_number_consistency") == "pass"

    def test_authority_without_bar_number_warns(self):
        data = {
            "licensing_authority": _g28_field("California State Bar"),
            "bar_number":          _g28_field(None, confidence=None),
        }
        result = verify_g28_fields(data)
        assert _check_status(result, "bar_number_consistency") == "warning"

    def test_neither_present_skips_check(self):
        data = {
            "licensing_authority": _g28_field(None, confidence=None),
            "bar_number":          _g28_field(None, confidence=None),
        }
        result = verify_g28_fields(data)
        assert _check_status(result, "bar_number_consistency") is None


class TestLabelContamination:
    def test_clean_fields_pass(self):
        data = {
            "last_name":  _g28_field("Smith"),
            "first_name": _g28_field("John"),
        }
        result = verify_g28_fields(data)
        assert _check_status(result, "label_contamination") == "pass"

    def test_label_text_in_field_warns(self):
        data = {
            "last_name": _g28_field("Part 1 Attorney or Accredited Rep"),
        }
        result = verify_g28_fields(data)
        assert _check_status(result, "label_contamination") == "warning"
