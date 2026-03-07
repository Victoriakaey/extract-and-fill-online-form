"""
G-28 AcroForm extraction.

Primary extraction path for fillable G-28 PDFs. Reads widget annotation
values directly from the PDF rather than parsing visual text.

Two-pass approach:
  Pass 1 — field name → canonical key (primary mapping)
  Pass 2 — value-type validation and relocation
            (only relocates if the target slot is currently empty)
"""
import re
from io import BytesIO

import pypdf

# ---------------------------------------------------------------------------
# Primary mapping: internal PDF field name prefix → canonical attorney key
# ---------------------------------------------------------------------------

G28_PRIMARY_MAP = {
    # Part 1 — Attorney/Representative
    "Pt1Line2a_FamilyName":                  "last_name",
    "Pt1Line2b_GivenName":                   "first_name",
    "Pt1Line2c_MiddleName":                  "middle_name",
    "Line3a_StreetNumber":                   "street_address",
    "Line3b_AptSteFlrNumber":                "apt_ste_flr_number",
    "Line3c_CityOrTown":                     "city",
    "Line3d_State":                          "state",
    "Line3e_ZipCode":                        "zip_code",
    "Line3h_Country":                        "country",
    "Line3g_PostalCode":                     "zip_code",       # international equivalent — first-wins in Pass 1,
                                                               # so Line3e wins if present; Line3g used otherwise
    "Line4_DaytimeTelephoneNumber":          "daytime_phone",
    "Line5_DaytimeTelephoneNumber":          "daytime_phone",  # alternate field naming
    "Line5_MobileTelephoneNumber":           "mobile_phone",
    "Line6_EMail":                           "email",
    "Line7_MobileTelephoneNumber":           "mobile_phone",   # seen in some G-28 versions
    "Pt1Line1_OnlineAccountNumber":          "online_account_number",
    # Part 2 — Eligibility
    "Pt2Line1a_LicensingAuthority":          "licensing_authority",
    "Pt2Line1b_BarNumber":                   "bar_number",
    "Pt2Line1d_NameofFirmOrOrganization":    "firm_name",
}

# All canonical attorney keys — any not populated by extraction will be null
_ALL_ATTORNEY_KEYS = [
    "online_account_number", "last_name", "first_name", "middle_name",
    "street_address", "apt_ste_flr_type", "apt_ste_flr_number",
    "city", "state", "zip_code", "country",
    "daytime_phone", "mobile_phone", "email",
    "licensing_authority", "bar_number", "subject_to_restrictions", "firm_name",
]

# Checkbox prefixes for subject_to_restrictions
_CHECKBOX_NOT_SUBJECT = "Checkbox1dAmNot"
_CHECKBOX_SUBJECT = "Checkbox1dAm"

# Unit type checkboxes in order: apt, ste, flr
_UNIT_CHECKBOXES = [
    ("Line3b_Unit[0]", "apt"),
    ("Line3b_Unit[1]", "ste"),
    ("Line3b_Unit[2]", "flr"),
]

# Values treated as "no data present"
_NULL_VALUES = frozenset({"N/A", "N/a", "n/a", "NA", ""})

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_PHONE_RE = re.compile(r'^\+?[\d\s\-\(\)\.]{7,20}$')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_index(name: str) -> str:
    """'FieldName[0]' → 'FieldName'"""
    bracket = name.find("[")
    return name[:bracket] if bracket != -1 else name


def _normalize(value: str) -> str | None:
    """Return None for null-sentinel values, stripped string otherwise."""
    stripped = value.strip()
    if not stripped or stripped in _NULL_VALUES or stripped == "/Off":
        return None
    return stripped


def _value_type(value: str) -> str:
    if _EMAIL_RE.match(value):
        return "email"
    if _PHONE_RE.match(value):
        return "phone"
    return "text"


def _field(value, confidence, warnings: list) -> dict:
    return {
        "value": value,
        "confidence": confidence if value is not None else None,
        "source": "g28",
        "warnings": warnings,
    }


def _read_widgets(pdf_bytes: bytes) -> tuple[dict, int]:
    """
    Read all AcroForm widget annotations.

    Returns (raw, skipped) where raw is {field_name: raw_value} and skipped
    is the count of annotations that raised an exception during parsing.
    """
    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    raw = {}
    skipped = 0
    for page in reader.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot in annots:
            try:
                obj = annot.get_object()
                if obj.get("/Subtype") != "/Widget":
                    continue
                name = str(obj.get("/T", ""))
                value = str(obj.get("/V", ""))
                if name:
                    raw[name] = value
            except Exception:
                skipped += 1
    return raw, skipped


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_g28_acroform(pdf_bytes: bytes) -> tuple[dict, list[str]] | tuple[None, None]:
    """
    Extract G-28 attorney fields from PDF AcroForm widget annotations.

    Returns (attorney, parse_warnings) on success, or (None, None) if the PDF
    does not contain enough AcroForm data (caller should fall back to LLM extraction).

    parse_warnings contains any non-fatal issues encountered during annotation
    parsing (e.g. skipped annotations due to malformed PDF objects).

    subject_to_restrictions is represented as bool:
      False = attorney is NOT subject to disciplinary restrictions
      True  = attorney IS subject to disciplinary restrictions
      None  = checkbox state could not be determined
    """
    try:
        raw, skipped = _read_widgets(pdf_bytes)
    except Exception:
        return None, None

    if not raw:
        return None, None

    parse_warnings: list[str] = []
    if skipped:
        parse_warnings.append(
            f"AcroForm parsing skipped {skipped} annotation(s) due to malformed PDF objects — "
            "some fields may be missing"
        )

    # -----------------------------------------------------------------------
    # Pass 1: primary name-based mapping
    # First occurrence wins — handles fields that appear on multiple pages.
    # -----------------------------------------------------------------------
    attorney: dict[str, dict] = {}

    for raw_name, raw_value in raw.items():
        base = _strip_index(raw_name)
        canonical_key = G28_PRIMARY_MAP.get(base)
        if canonical_key is None or canonical_key in attorney:
            continue
        value = _normalize(raw_value)
        attorney[canonical_key] = _field(value, 1.0, [])

    # -----------------------------------------------------------------------
    # Checkbox: subject_to_restrictions (boolean)
    # -----------------------------------------------------------------------
    not_subject = any(
        v == "/Y" for k, v in raw.items()
        if _strip_index(k) == _CHECKBOX_NOT_SUBJECT
    )
    is_subject = any(
        v == "/Y" for k, v in raw.items()
        if _strip_index(k) == _CHECKBOX_SUBJECT
    )
    if not_subject:
        attorney["subject_to_restrictions"] = _field(False, 1.0, [])
    elif is_subject:
        attorney["subject_to_restrictions"] = _field(True, 1.0, [])
    else:
        attorney["subject_to_restrictions"] = _field(
            None, None, ["checkbox state could not be determined"]
        )

    # -----------------------------------------------------------------------
    # Checkbox group: apt_ste_flr_type
    # -----------------------------------------------------------------------
    apt_type = None
    for field_name, unit_label in _UNIT_CHECKBOXES:
        if raw.get(field_name) == "/Y":
            apt_type = unit_label
            break
    attorney["apt_ste_flr_type"] = _field(apt_type, 1.0 if apt_type else None, [])

    # -----------------------------------------------------------------------
    # Pass 2: value-type validation and relocation
    # Relocation only happens when the target slot is currently empty (None).
    # -----------------------------------------------------------------------
    for key, entry in list(attorney.items()):
        value = entry.get("value")
        if not value:
            continue

        vtype = _value_type(value)

        # Phone field contains an email value
        if key in ("mobile_phone", "daytime_phone") and vtype == "email":
            if attorney.get("email", {}).get("value") is None:
                attorney["email"] = _field(
                    value, 0.85,
                    [f"relocated from '{key}': email pattern found in phone field"]
                )
                attorney[key] = _field(
                    None, None, ["value relocated — see email field"]
                )

        # Email field contains a phone value
        elif key == "email" and vtype == "phone":
            if attorney.get("mobile_phone", {}).get("value") is None:
                attorney["mobile_phone"] = _field(
                    value, 0.85,
                    ["relocated from 'email': phone pattern found in email field"]
                )
                attorney[key] = _field(
                    None, None, ["value relocated — see mobile_phone field"]
                )

    # -----------------------------------------------------------------------
    # Fill remaining canonical keys as null
    # -----------------------------------------------------------------------
    for k in _ALL_ATTORNEY_KEYS:
        if k not in attorney:
            attorney[k] = _field(None, None, ["field not found in PDF"])

    # -----------------------------------------------------------------------
    # Reject if too sparse to be useful
    # -----------------------------------------------------------------------
    non_null = sum(1 for v in attorney.values() if v.get("value") is not None)
    if non_null < 3:
        return None, None

    return attorney, parse_warnings
