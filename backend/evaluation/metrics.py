"""
Lightweight field-level accuracy helper for evaluating extraction quality
against known ground-truth values.

Usage:
    from backend.evaluation.metrics import compute_field_accuracy

    result = compute_field_accuracy(
        expected={"last_name": "LEE", "passport_number": "M70689098", ...},
        extracted=beneficiary_section,  # canonical dict with {value, confidence, ...}
    )
    print(result)

Not a benchmarking framework — intended for quick spot-checks on sample files.
"""


def compute_field_accuracy(expected: dict, extracted: dict) -> dict:
    """
    Compare expected values against extracted canonical fields.

    Args:
        expected:  flat dict of {field_name: expected_value_string}
                   Fields mapped to None are skipped (treated as unknown).
        extracted: canonical section dict {field_name: {value, confidence, source, warnings}}

    Returns:
        {
            "correct_fields": int,
            "total_fields":   int,
            "accuracy":       float,        # 0.0–1.0
            "mismatches":     {field: {"expected": ..., "extracted": ...}},
        }
    """
    correct = 0
    total = 0
    mismatches: dict = {}

    for field, expected_value in expected.items():
        if expected_value is None:
            continue
        total += 1

        field_data = extracted.get(field, {})
        extracted_value = field_data.get("value") if isinstance(field_data, dict) else field_data

        # Normalise for comparison: strip whitespace, case-insensitive
        exp_norm = str(expected_value).strip().lower()
        ext_norm = str(extracted_value).strip().lower() if extracted_value is not None else ""

        if exp_norm == ext_norm:
            correct += 1
        else:
            mismatches[field] = {"expected": expected_value, "extracted": extracted_value}

    return {
        "correct_fields": correct,
        "total_fields": total,
        "accuracy": round(correct / total, 3) if total else 0.0,
        "mismatches": mismatches,
    }
