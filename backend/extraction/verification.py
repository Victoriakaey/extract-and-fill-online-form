"""
Lightweight deterministic verification for extracted passport and G-28 fields.

Rules:
  - Never block execution
  - Never delete or overwrite extracted values
  - Only append warnings to field metadata
  - Return a flat list of verification warnings for the trace
"""

import re
from datetime import date

_PASSPORT_NUMBER_RE = re.compile(r'^[A-Z0-9]{6,9}$')
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_ZIP_RE = re.compile(r'^\d{5}(-\d{4})?$')

# Heuristic: G-28 label/instruction contamination — text that reads like a form header
_LABEL_RE = re.compile(
    r'\b(part\s+\d|see\s+instructions?|attorney\s+or|accredited\s+rep|notice\s+of\s+entry)\b',
    re.IGNORECASE,
)


def _val(section: dict, key: str):
    field = section.get(key)
    if not isinstance(field, dict):
        return None
    return field.get("value")


def _append_warning(section: dict, key: str, message: str) -> None:
    field = section.get(key)
    if isinstance(field, dict):
        field.setdefault("warnings", []).append(message)


def _parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        return None


def verify_passport_fields(data: dict) -> list[str]:
    """
    Validate extracted passport fields and append warnings for suspicious values.

    Args:
        data: the beneficiary section dict (field_name → {value, confidence, source, warnings})

    Returns:
        List of verification warning strings added during this call (for trace inclusion).
    """
    added: list[str] = []

    def warn(key: str, message: str) -> None:
        _append_warning(data, key, message)
        added.append(message)

    # passport_number: 6–9 uppercase alphanumeric characters
    pn = _val(data, "passport_number")
    if pn is not None and not _PASSPORT_NUMBER_RE.match(str(pn)):
        warn("passport_number", "passport number format unexpected")

    # sex: must be M, F, or X
    sex = _val(data, "sex")
    if sex is not None and sex not in ("M", "F", "X"):
        warn("sex", "sex value unexpected — expected M, F, or X")

    # date ordering: date_of_birth < date_of_issue < date_of_expiration
    dob = _parse_date(_val(data, "date_of_birth"))
    doi = _parse_date(_val(data, "date_of_issue"))
    doe = _parse_date(_val(data, "date_of_expiration"))

    if dob and doi and doe and not (dob < doi < doe):
        msg = "passport date ordering inconsistent"
        for key in ("date_of_birth", "date_of_issue", "date_of_expiration"):
            _append_warning(data, key, msg)
        added.append(msg)

    return added


def verify_g28_fields(data: dict) -> list[str]:
    """
    Validate attorney fields extracted from the G-28 form and append warnings
    for suspicious values.

    Args:
        data: the attorney section dict (field_name → {value, confidence, source, warnings})

    Returns:
        List of verification warning strings added during this call (for trace inclusion).
    """
    added: list[str] = []

    def warn(key: str, message: str) -> None:
        _append_warning(data, key, message)
        added.append(message)

    # email: basic format check
    email = _val(data, "email")
    if email is not None and not _EMAIL_RE.match(str(email)):
        warn("email", "email format suspicious")

    # zip_code: US ZIP format (5-digit or ZIP+4)
    zip_code = _val(data, "zip_code")
    if zip_code is not None and not _ZIP_RE.match(str(zip_code)):
        warn("zip_code", "zip code format unexpected")

    # bar_number: if licensing_authority is present, bar_number should be too
    if _val(data, "licensing_authority") is not None and _val(data, "bar_number") is None:
        warn("bar_number", "bar number missing — licensing authority is present")

    # label contamination: name/address fields that look like form headers or instructions
    for key in ("last_name", "first_name", "middle_name", "street_address", "city", "firm_name"):
        value = _val(data, key)
        if value and _LABEL_RE.search(str(value)):
            warn(key, "value may be a form label rather than extracted content")

    return added
