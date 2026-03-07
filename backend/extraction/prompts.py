PASSPORT_EXTRACTION_PROMPT = """Extract the following fields from this passport image.

For each named field return a JSON object with:
  - "value": the extracted string, or null if not visible or not present
  - "confidence": a rough indicator from 0.0 to 1.0 of how clearly the field is visible
  - "warnings": a list of strings describing any issues (empty list if none)

Rules:
  - Only extract information clearly visible in the document.
  - Do not infer, guess, or derive values from other fields.
  - If a field is absent or unreadable, set value to null and add a warning.
  - Normalize all dates to YYYY-MM-DD format.
  - For sex, return "M", "F", or "X" only.
  - For passport_number: extract the document number from the printed data field only,
    not from the MRZ strip. Passport numbers are typically 6–9 alphanumeric characters.
    Do not include the single-digit MRZ check digit that follows the number in the MRZ line.

Fields to extract (each as a JSON object with value/confidence/warnings):
last_name, first_name, middle_name, passport_number, country_of_issue,
nationality, date_of_birth, place_of_birth, sex, date_of_issue, date_of_expiration

Additionally, extract the two MRZ lines at the bottom of the passport.
These lines are in the Machine Readable Zone (MRZ) printed in monospace at the bottom of the data page.

Rules for MRZ extraction:
  - Each line must be exactly 44 characters long.
  - The "<" character is a filler and must be preserved exactly as printed — do NOT strip or replace it.
  - Copy every character as-is, including all "<" fillers between and after names.
  - Example line 1 shape: P<GBRSMITH<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<
  - Example line 2 shape: 1234567897GBR8001011M3001019<<<<<<<<<<<<6

Return:
  - "mrz_line1": the first MRZ line as a plain string (exactly 44 characters, preserving all "<" fillers)
  - "mrz_line2": the second MRZ line as a plain string (exactly 44 characters, preserving all "<" fillers)

Return mrz_line1 and mrz_line2 as plain strings, not JSON objects.

Return only a valid JSON object. No explanation.
"""

G28_EXTRACTION_PROMPT = """Extract the following fields from this G-28 form \
(Notice of Entry of Appearance as Attorney or Accredited Representative).

For each field return a JSON object with:
  - "value": the extracted string, or null if blank or not present
  - "confidence": a rough indicator from 0.0 to 1.0 of how clearly the field is readable
  - "warnings": a list of strings describing any issues (empty list if none)

Rules:
  - Only extract information clearly present in the document.
  - Do not infer or guess missing values.
  - If a field is blank or unreadable, set value to null and add a warning.
  - For subject_to_restrictions: return "not" if "am not" is checked, \
"am" if "am" is checked, null if unclear.
  - For apt_ste_flr_type: return one of "apt", "ste", "flr", or null.

Fields to extract:
online_account_number, last_name, first_name, middle_name,
street_address, apt_ste_flr_type, apt_ste_flr_number, city, state, zip_code, country,
daytime_phone, mobile_phone, email,
licensing_authority, bar_number, subject_to_restrictions, firm_name

Return only a valid JSON object with these exact field names as keys. No explanation.
"""
