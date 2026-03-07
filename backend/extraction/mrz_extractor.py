"""
MRZ parsing and validation for passport extraction.

Used as the authoritative source for key passport fields when the LLM
extracts valid MRZ lines from the passport image.

Fields provided by MRZ (confidence = 1.0 when checksums pass):
  passport_number, nationality, date_of_birth, date_of_expiration,
  sex, last_name, first_name, country_of_issue

Fields NOT in MRZ (remain as LLM visual values):
  middle_name, place_of_birth, date_of_issue
"""
from datetime import date as Date

from mrz.checker.td3 import TD3CodeChecker


def _year_dob(yy: str) -> str:
    """
    Convert 2-digit DOB year to 4-digit.
    Rule: if YY > current year's 2-digit → 1900s, else 2000s.
    E.g. in 2026: YY=85 → 1985, YY=10 → 2010.
    """
    y = int(yy)
    current_2d = Date.today().year % 100
    return f"19{yy}" if y > current_2d else f"20{yy}"


def _year_expiry(yy: str) -> str:
    """Expiry dates on valid passports are always in the future → 20XX."""
    return f"20{yy}"


def _mrz_date(yymmdd: str, is_dob: bool = False) -> str | None:
    """Convert YYMMDD → YYYY-MM-DD, or None if malformed."""
    if not yymmdd or len(yymmdd) != 6 or not yymmdd.isdigit():
        return None
    yy, mm, dd = yymmdd[:2], yymmdd[2:4], yymmdd[4:]
    year = _year_dob(yy) if is_dob else _year_expiry(yy)
    return f"{year}-{mm}-{dd}"


def _clean(value: str) -> str | None:
    """Strip MRZ filler '<' characters and whitespace. Return None if empty."""
    cleaned = value.replace("<", " ").strip()
    return cleaned or None


def parse_mrz(line1: str, line2: str) -> dict | None:
    """
    Validate MRZ lines using checksum validation and return canonical overrides.

    Args:
        line1: first MRZ line (should be 44 chars)
        line2: second MRZ line (should be 44 chars)

    Returns:
        dict of canonical field overrides if all checksums pass,
        None if lines are missing, malformed, or checksums fail
        (caller falls back to LLM visual values in that case).
    """
    if not line1 or not line2:
        return None

    # Normalize: uppercase, collapse spaces to filler
    line1 = line1.upper().strip().replace(" ", "<")
    line2 = line2.upper().strip().replace(" ", "<")

    if len(line1) != 44 or len(line2) != 44:
        return None

    try:
        checker = TD3CodeChecker(line1 + "\n" + line2)
    except Exception:
        return None

    if not checker:  # one or more checksums failed
        return None

    f = checker.fields()

    return {
        "passport_number":    _clean(f.document_number),
        "nationality":        _clean(f.nationality),
        "date_of_birth":      _mrz_date(f.birth_date, is_dob=True),
        "date_of_expiration": _mrz_date(f.expiry_date, is_dob=False),
        "sex":                f.sex if f.sex in ("M", "F", "X") else None,
        "last_name":          _clean(f.surname),
        "first_name":         _clean(f.name),
        "country_of_issue":   _clean(f.country),
    }
