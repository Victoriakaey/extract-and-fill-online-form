"""
Playwright form automation for the target submission form.

Takes the full canonical extraction object (beneficiary + attorney) and fills
the target form without submitting it. The browser stays open after filling
so the user can review the populated fields.

Field mapping source: docs/schema-and-mapping.md
"""

from playwright.sync_api import sync_playwright

TARGET_URL = "https://mendrika-alma.github.io/form-submission/"


def _val(section: dict, key: str):
    """Return the value from a canonical field dict, or None if absent/null."""
    field = section.get(key)
    if not isinstance(field, dict):
        return None
    return field.get("value")


def fill_form(canonical: dict) -> dict:
    """
    Open the target form and fill all extractable fields from the canonical object.

    Args:
        canonical: {"beneficiary": {...}, "attorney": {...}}

    Returns:
        {"filled": [...], "skipped": [...], "errors": [...]}

    The browser stays open after filling (user must close manually). The form
    is never submitted.
    """
    beneficiary = canonical.get("beneficiary", {})
    attorney = canonical.get("attorney", {})
    filled: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    def fill_text(selector: str, value, label: str):
        if value is None:
            skipped.append(label)
            return
        try:
            page.fill(selector, str(value))
            filled.append(label)
        except Exception as e:
            errors.append(f"{label}: {e}")

    def select_opt(selector: str, value, label: str):
        if value is None:
            skipped.append(label)
            return
        try:
            page.select_option(selector, str(value))
            filled.append(label)
        except Exception as e:
            errors.append(f"{label}: {e}")

    def check_box(selector: str, label: str):
        try:
            loc = page.locator(selector)
            if not loc.is_checked():
                loc.check()
            filled.append(label)
        except Exception as e:
            errors.append(f"{label}: {e}")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=80)
    page = browser.new_page()
    page.goto(TARGET_URL)
    page.wait_for_load_state("networkidle")

    try:
        # -----------------------------------------------------------------
        # Part 1 — Beneficiary (passport fields)
        # -----------------------------------------------------------------
        fill_text("#passport-surname",    _val(beneficiary, "last_name"),        "beneficiary.last_name")
        fill_text("#passport-given-names", _val(beneficiary, "first_name"),      "beneficiary.first_name")

        # middle_name shares id="passport-given-names" — use positional selector
        middle = _val(beneficiary, "middle_name")
        if middle is not None:
            try:
                page.locator('input[name="passport-given-names"]').nth(1).fill(str(middle))
                filled.append("beneficiary.middle_name")
            except Exception as e:
                errors.append(f"beneficiary.middle_name: {e}")
        else:
            skipped.append("beneficiary.middle_name")

        fill_text("#passport-number",      _val(beneficiary, "passport_number"),   "beneficiary.passport_number")
        fill_text("#passport-country",     _val(beneficiary, "country_of_issue"),  "beneficiary.country_of_issue")
        fill_text("#passport-nationality", _val(beneficiary, "nationality"),       "beneficiary.nationality")
        fill_text("#passport-dob",         _val(beneficiary, "date_of_birth"),     "beneficiary.date_of_birth")
        fill_text("#passport-pob",         _val(beneficiary, "place_of_birth"),    "beneficiary.place_of_birth")
        select_opt("#passport-sex",        _val(beneficiary, "sex"),               "beneficiary.sex")
        fill_text("#passport-issue-date",  _val(beneficiary, "date_of_issue"),     "beneficiary.date_of_issue")
        fill_text("#passport-expiry-date", _val(beneficiary, "date_of_expiration"), "beneficiary.date_of_expiration")

        # -----------------------------------------------------------------
        # Part 2 — Attorney (G-28 fields)
        # -----------------------------------------------------------------
        fill_text("#online-account",      _val(attorney, "online_account_number"), "attorney.online_account_number")
        fill_text("#family-name",         _val(attorney, "last_name"),             "attorney.last_name")
        fill_text("#given-name",          _val(attorney, "first_name"),            "attorney.first_name")
        fill_text("#middle-name",         _val(attorney, "middle_name"),           "attorney.middle_name")
        fill_text("#street-number",       _val(attorney, "street_address"),        "attorney.street_address")

        # apt_ste_flr_type — three-checkbox group, tick the matching one
        apt_type = _val(attorney, "apt_ste_flr_type")
        if apt_type in ("apt", "ste", "flr"):
            check_box(f"#{apt_type}", "attorney.apt_ste_flr_type")
        else:
            skipped.append("attorney.apt_ste_flr_type")

        fill_text("#apt-number",          _val(attorney, "apt_ste_flr_number"),   "attorney.apt_ste_flr_number")
        fill_text("#city",                _val(attorney, "city"),                 "attorney.city")
        select_opt("#state",              _val(attorney, "state"),                "attorney.state")
        fill_text("#zip",                 _val(attorney, "zip_code"),             "attorney.zip_code")
        fill_text("#country",             _val(attorney, "country"),              "attorney.country")
        fill_text("#daytime-phone",       _val(attorney, "daytime_phone"),        "attorney.daytime_phone")
        fill_text("#mobile-phone",        _val(attorney, "mobile_phone"),         "attorney.mobile_phone")
        fill_text("#email",               _val(attorney, "email"),                "attorney.email")
        fill_text("#licensing-authority", _val(attorney, "licensing_authority"),  "attorney.licensing_authority")
        fill_text("#bar-number",          _val(attorney, "bar_number"),           "attorney.bar_number")

        # subject_to_restrictions — boolean (False = not subject, True = subject)
        # Also handles LLM string variants "not" / "am" as a fallback
        restriction = _val(attorney, "subject_to_restrictions")
        if restriction is False or restriction == "not":
            check_box("#not-subject", "attorney.subject_to_restrictions")
        elif restriction is True or restriction == "am":
            check_box("#am-subject",  "attorney.subject_to_restrictions")
        else:
            skipped.append("attorney.subject_to_restrictions")

        fill_text("#law-firm", _val(attorney, "firm_name"), "attorney.firm_name")

        # -----------------------------------------------------------------
        # Keep browser open for review — do NOT submit
        # -----------------------------------------------------------------
        page.wait_for_event("close", timeout=0)

    finally:
        try:
            browser.close()
        except Exception:
            pass
        pw.stop()

    return {"filled": filled, "skipped": skipped, "errors": errors}
