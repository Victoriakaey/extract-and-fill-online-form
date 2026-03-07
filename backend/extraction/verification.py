"""
Lightweight deterministic verification for extracted passport and G-28 fields.

Rules:
  - Never block execution
  - Never delete or overwrite extracted values
  - Only append warnings to field metadata
  - Return warnings (for trace) and checks (for report) from each function
"""

import re
from datetime import date

_PASSPORT_NUMBER_RE = re.compile(r'^[A-Z0-9]{6,12}$')
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_ZIP_RE = re.compile(r'^\d{5}(-\d{4})?$')

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


def verify_passport_fields(data: dict) -> dict:
    """
    Validate extracted passport fields.

    Returns:
        {
            "warnings": [str, ...],         # flat list for trace / UI
            "checks":   [{check, status, ?message}, ...]  # per-rule results for report
        }
    Mutates field-level warnings in data. Never blocks execution.
    """
    warnings: list[str] = []
    checks:   list[dict] = []

    def passed(name: str) -> None:
        checks.append({"check": name, "status": "pass"})

    def warned(name: str, message: str, keys: list[str] | None = None) -> None:
        checks.append({"check": name, "status": "warning", "message": message})
        warnings.append(message)
        for key in (keys or []):
            _append_warning(data, key, message)

    # passport_number_format
    pn = _val(data, "passport_number")
    if pn is not None:
        if _PASSPORT_NUMBER_RE.match(str(pn)):
            passed("passport_number_format")
        else:
            warned("passport_number_format", "passport number format unexpected", ["passport_number"])

    # sex_value
    sex = _val(data, "sex")
    if sex is not None:
        if sex in ("M", "F", "X"):
            passed("sex_value")
        else:
            warned("sex_value", "sex value unexpected — expected M, F, or X", ["sex"])

    # date_ordering
    dob = _parse_date(_val(data, "date_of_birth"))
    doi = _parse_date(_val(data, "date_of_issue"))
    doe = _parse_date(_val(data, "date_of_expiration"))
    if dob and doi and doe:
        if dob < doi < doe:
            passed("date_ordering")
        else:
            warned("date_ordering", "passport date ordering inconsistent",
                   ["date_of_birth", "date_of_issue", "date_of_expiration"])
    elif any([dob, doi, doe]):
        missing = [k for k, v in [("date_of_birth", dob), ("date_of_issue", doi), ("date_of_expiration", doe)] if not v]
        warned("date_ordering", f"date ordering check skipped — missing: {', '.join(missing)}")

    return {"warnings": warnings, "checks": checks}


def verify_g28_fields(data: dict) -> dict:
    """
    Validate attorney fields extracted from the G-28 form.

    Returns:
        {
            "warnings": [str, ...],
            "checks":   [{check, status, ?message}, ...]
        }
    Mutates field-level warnings in data. Never blocks execution.
    """
    warnings: list[str] = []
    checks:   list[dict] = []

    def passed(name: str) -> None:
        checks.append({"check": name, "status": "pass"})

    def warned(name: str, message: str, keys: list[str] | None = None) -> None:
        checks.append({"check": name, "status": "warning", "message": message})
        warnings.append(message)
        for key in (keys or []):
            _append_warning(data, key, message)

    # email_format
    email = _val(data, "email")
    if email is not None:
        if _EMAIL_RE.match(str(email)):
            passed("email_format")
        else:
            warned("email_format", "email format suspicious", ["email"])

    # zip_code_format
    zip_code = _val(data, "zip_code")
    if zip_code is not None:
        if _ZIP_RE.match(str(zip_code)):
            passed("zip_code_format")
        else:
            warned("zip_code_format", "zip code format unexpected", ["zip_code"])

    # bar_number_consistency
    licensing_authority = _val(data, "licensing_authority")
    bar_number          = _val(data, "bar_number")
    if licensing_authority is not None:
        if bar_number is not None:
            passed("bar_number_consistency")
        else:
            warned("bar_number_consistency", "bar number missing — licensing authority is present", ["bar_number"])

    # label_contamination
    contaminated = []
    for key in ("last_name", "first_name", "middle_name", "street_address", "city", "firm_name"):
        value = _val(data, key)
        if value and _LABEL_RE.search(str(value)):
            _append_warning(data, key, "value may be a form label rather than extracted content")
            contaminated.append(key)
    if contaminated:
        warned("label_contamination",
               f"possible label contamination in: {', '.join(contaminated)}")
    else:
        passed("label_contamination")

    return {"warnings": warnings, "checks": checks}
